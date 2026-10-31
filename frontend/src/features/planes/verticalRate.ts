/**
 * A plane's `alt_v` is its smoothed vertical rate in feet per minute, positive when climbing.
 *
 * Within this rate either way a plane counts as level. Real climbs and descents are faster
 * (an approach descends at about 700 ft/min). A plane holding its altitude almost always
 * stays inside it: in simulation, with 25 ft altitude steps and ±20 ft of jitter, up to
 * about 1% of its updates cross it.
 */
export const LEVEL_FLIGHT_MAX_FPM = 300;
