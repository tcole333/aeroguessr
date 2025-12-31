#!/usr/bin/env python3
# ruff: noqa: T201, E501
"""
Raw ADS-B Data Quality Analyzer
Captures and analyzes raw SBS-1 data from dump1090 to identify data quality issues.

Note: This is a CLI script that uses print statements intentionally for user output.
"""

import math
import socket
import time
from collections import defaultdict
from typing import Dict, List, Tuple


class FlightMessage:
    """Represents a single ADS-B message"""

    def __init__(self, raw_line: str) -> None:
        self.raw = raw_line.strip()
        self.timestamp = time.time()
        self.fields = self.raw.split(",")

        # SBS-1 format fields
        self.msg_type = self.fields[0] if len(self.fields) > 0 else None
        self.hex_ident = self.fields[4] if len(self.fields) > 4 else None
        self.callsign = self.fields[10] if len(self.fields) > 10 and self.fields[10] else None

        # Position data (MSG type 3)
        self.lat = float(self.fields[14]) if len(self.fields) > 14 and self.fields[14] else None
        self.lon = float(self.fields[15]) if len(self.fields) > 15 and self.fields[15] else None
        self.altitude = int(self.fields[11]) if len(self.fields) > 11 and self.fields[11] else None

        # Velocity data (MSG type 4)
        self.ground_speed = (
            int(self.fields[12]) if len(self.fields) > 12 and self.fields[12] else None
        )
        self.track = int(self.fields[13]) if len(self.fields) > 13 and self.fields[13] else None

        # Message subtype
        self.transmission_type = (
            int(self.fields[1]) if len(self.fields) > 1 and self.fields[1] else None
        )


class FlightTracker:
    """Tracks a single flight and analyzes data quality"""

    def __init__(self, hex_ident: str) -> None:
        self.hex_ident = hex_ident
        self.callsign = None
        self.messages: List[FlightMessage] = []
        self.position_updates: List[
            Tuple[float, float, float, float]
        ] = []  # (timestamp, lat, lon, alt)
        self.start_time = time.time()
        self.position_jumps: List[Dict] = []
        self.update_gaps: List[float] = []
        self.last_update_time = None

    def add_message(self, msg: FlightMessage) -> None:
        """Add a message to this flight's history"""
        self.messages.append(msg)

        # Update callsign if available
        if msg.callsign:
            self.callsign = msg.callsign

        # Track update gaps
        if self.last_update_time:
            gap = msg.timestamp - self.last_update_time
            self.update_gaps.append(gap)
        self.last_update_time = msg.timestamp

        # Track position updates
        if msg.lat is not None and msg.lon is not None:
            self.position_updates.append((msg.timestamp, msg.lat, msg.lon, msg.altitude))

            # Check for position jumps
            if len(self.position_updates) >= 2:
                self._check_position_jump()

    def _check_position_jump(self) -> None:
        """Check for unrealistic position jumps between last two updates"""
        if len(self.position_updates) < 2:
            return

        prev = self.position_updates[-2]
        curr = self.position_updates[-1]

        # Calculate time delta
        time_delta = curr[0] - prev[0]

        # Calculate distance using haversine formula
        lat1, lon1 = math.radians(prev[1]), math.radians(prev[2])
        lat2, lon2 = math.radians(curr[1]), math.radians(curr[2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Distance in degrees (approximate)
        distance_deg = math.degrees(c)

        # Speed in degrees per second
        if time_delta > 0:
            speed_deg_per_sec = distance_deg / time_delta

            # Check for jumps
            if distance_deg > 5.0:  # Extreme jump
                self.position_jumps.append(
                    {
                        "distance_deg": distance_deg,
                        "time_delta": time_delta,
                        "speed_deg_per_sec": speed_deg_per_sec,
                        "from": (prev[1], prev[2]),
                        "to": (curr[1], curr[2]),
                        "severity": "EXTREME",
                    }
                )
            elif speed_deg_per_sec > 0.17:  # Unrealistic speed (>600 knots)
                self.position_jumps.append(
                    {
                        "distance_deg": distance_deg,
                        "time_delta": time_delta,
                        "speed_deg_per_sec": speed_deg_per_sec,
                        "from": (prev[1], prev[2]),
                        "to": (curr[1], curr[2]),
                        "severity": "HIGH",
                    }
                )

    def analyze(self) -> Dict:
        """Analyze the collected data and return a report"""
        tracking_duration = time.time() - self.start_time

        # Message type breakdown
        msg_types = defaultdict(int)
        for msg in self.messages:
            if msg.transmission_type:
                msg_types[msg.transmission_type] += 1

        # Position update analysis
        position_count = len(self.position_updates)
        avg_position_interval = tracking_duration / position_count if position_count > 0 else 0

        # Update gap analysis
        if self.update_gaps:
            avg_gap = sum(self.update_gaps) / len(self.update_gaps)
            max_gap = max(self.update_gaps)
            gaps_over_5s = sum(1 for g in self.update_gaps if g > 5.0)
        else:
            avg_gap = max_gap = gaps_over_5s = 0

        # Data completeness
        msgs_with_callsign = sum(1 for m in self.messages if m.callsign)
        msgs_with_altitude = sum(1 for m in self.messages if m.altitude is not None)
        msgs_with_speed = sum(1 for m in self.messages if m.ground_speed is not None)

        # Calculate data quality score (0-100)
        score = 100
        score -= len(self.position_jumps) * 10  # Deduct for jumps
        score -= gaps_over_5s * 5  # Deduct for long gaps
        score -= 10 if position_count < 10 else 0  # Deduct for few updates
        score = max(0, score)

        return {
            "hex_ident": self.hex_ident,
            "callsign": self.callsign or "Unknown",
            "tracking_duration": tracking_duration,
            "total_messages": len(self.messages),
            "message_types": dict(msg_types),
            "position_updates": position_count,
            "avg_position_interval": avg_position_interval,
            "update_gaps": {"average": avg_gap, "max": max_gap, "gaps_over_5s": gaps_over_5s},
            "position_jumps": self.position_jumps,
            "data_completeness": {
                "with_callsign": f"{msgs_with_callsign}/{len(self.messages)}",
                "with_altitude": f"{msgs_with_altitude}/{len(self.messages)}",
                "with_speed": f"{msgs_with_speed}/{len(self.messages)}",
            },
            "quality_score": score,
        }


def capture_and_analyze(host: str = "localhost", port: int = 30003, duration: int = 120) -> None:
    """Capture ADS-B data and analyze quality"""
    print(f"Connecting to dump1090 at {host}:{port}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print("Connected! Monitoring for flights...")

        # Track flights
        flights: Dict[str, FlightTracker] = {}
        start_time = time.time()
        selected_flight = None

        while time.time() - start_time < duration:
            try:
                # Read line from dump1090
                data = sock.recv(1024).decode("ascii", errors="ignore")
                lines = data.strip().split("\n")

                for line in lines:
                    if not line or not line.startswith("MSG"):
                        continue

                    try:
                        msg = FlightMessage(line)

                        if msg.hex_ident:
                            # Track this flight
                            if msg.hex_ident not in flights:
                                flights[msg.hex_ident] = FlightTracker(msg.hex_ident)
                                print(f"New flight detected: {msg.hex_ident}")

                            flights[msg.hex_ident].add_message(msg)

                            # Select first flight with position data
                            if not selected_flight and msg.lat is not None:
                                selected_flight = msg.hex_ident
                                print(f"Focusing on flight: {selected_flight}")

                            # Print updates for selected flight
                            if msg.hex_ident == selected_flight:
                                if msg.lat is not None:
                                    print(
                                        f"  Position: {msg.lat:.4f}, {msg.lon:.4f} @ {msg.altitude}ft"
                                    )

                                    # Check for extreme jumps
                                    tracker = flights[msg.hex_ident]
                                    if tracker.position_jumps:
                                        latest_jump = tracker.position_jumps[-1]
                                        if latest_jump["severity"] == "EXTREME":
                                            print(
                                                f"  🚨 EXTREME JUMP: {latest_jump['distance_deg']:.2f}° in {latest_jump['time_delta']:.1f}s"
                                            )

                    except Exception as e:
                        print(f"Error parsing message: {e}")

            except socket.timeout:
                continue
            except Exception as e:
                print(f"Socket error: {e}")
                break

        # Analyze results
        print("\n" + "=" * 60)
        print("ANALYSIS RESULTS")
        print("=" * 60)

        # Focus on selected flight
        if selected_flight and selected_flight in flights:
            report = flights[selected_flight].analyze()

            print(f"\nFlight: {report['hex_ident']} ({report['callsign']})")
            print(f"Tracking Duration: {report['tracking_duration']:.1f} seconds")
            print(f"Total Messages: {report['total_messages']}")
            print(
                f"Position Updates: {report['position_updates']} (avg {report['avg_position_interval']:.1f}s between)"
            )

            print(f"\nMessage Types: {report['message_types']}")

            print("\nUpdate Gaps:")
            print(f"  Average: {report['update_gaps']['average']:.2f}s")
            print(f"  Maximum: {report['update_gaps']['max']:.2f}s")
            print(f"  Gaps >5s: {report['update_gaps']['gaps_over_5s']}")

            print("\nData Completeness:")
            for field, ratio in report["data_completeness"].items():
                print(f"  {field}: {ratio}")

            print(f"\nPosition Jumps: {len(report['position_jumps'])}")
            for jump in report["position_jumps"][:5]:  # Show first 5
                print(
                    f"  {jump['severity']}: {jump['distance_deg']:.4f}° in {jump['time_delta']:.1f}s"
                )
                print(f"    From: {jump['from']}")
                print(f"    To:   {jump['to']}")

            print(f"\nQUALITY SCORE: {report['quality_score']}/100")

            if report["quality_score"] < 50:
                print("\n⚠️  POOR DATA QUALITY DETECTED")
                if any(j["severity"] == "EXTREME" for j in report["position_jumps"]):
                    print("  - Extreme position jumps indicate data corruption")
                if report["update_gaps"]["gaps_over_5s"] > 5:
                    print("  - Frequent update gaps suggest reception issues")

        # Summary of all flights
        print(f"\n\nTotal flights tracked: {len(flights)}")
        for hex_id, tracker in list(flights.items())[:10]:  # Show first 10
            print(
                f"  {hex_id}: {len(tracker.messages)} messages, {len(tracker.position_updates)} positions"
            )

    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        sock.close()


if __name__ == "__main__":
    import sys

    # Allow command line args
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    print("ADS-B Raw Data Quality Analyzer")
    print(f"Host: {host}, Duration: {duration}s")
    print("-" * 60)

    capture_and_analyze(host=host, duration=duration)
