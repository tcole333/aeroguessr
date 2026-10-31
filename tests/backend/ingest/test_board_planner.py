"""Which board requests the refresher plans, and how far each answer covers."""

from backend.ingest.aeroapi_client import BoardEndpoint
from backend.ingest.board_refresher import (
    ARRIVALS_OVERLAP,
    COLD_MIN_COVERAGE,
    MIN_COVERAGE_STEP,
    MINUTE,
    Feed,
    FeedState,
    next_coverage,
    plan_requests,
)
from backend.ingest.enrichment_config import COLD_START_RESULT_SETS

NOW = 1_800_000_000.0


def test_cold_board_asks_each_endpoint_once_in_at_most_two_pages() -> None:
    requests = plan_requests(NOW, FeedState(), FeedState())

    assert [(r.endpoint, r.max_pages) for r in requests] == [
        (BoardEndpoint.SCHEDULED_ARRIVALS, 2),
        (BoardEndpoint.SCHEDULED_DEPARTURES, 2),
        (BoardEndpoint.DEPARTURES, 1),
    ]
    assert all(r.cold for r in requests)


def test_cold_start_reserves_exactly_the_minimum_the_config_allows() -> None:
    """The config rejects per-minute and daily limits that could not fund this tick."""
    requests = plan_requests(NOW, FeedState(), FeedState())

    assert sum(r.max_pages for r in requests) == COLD_START_RESULT_SETS


def test_well_covered_board_needs_nothing() -> None:
    covered = FeedState(covered_until=NOW + 60 * MINUTE)

    assert plan_requests(NOW, covered, covered) == []


def test_warm_arrivals_continue_from_coverage_with_a_small_overlap() -> None:
    arrivals = FeedState(covered_until=NOW + 15 * MINUTE)
    departures = FeedState(covered_until=NOW + 60 * MINUTE)

    [request] = plan_requests(NOW, arrivals, departures)

    assert request.feed is Feed.ARRIVALS
    assert request.max_pages == 1
    assert request.start == NOW + 15 * MINUTE - ARRIVALS_OVERLAP


def test_stale_coverage_after_a_break_starts_cold_again() -> None:
    stale = FeedState(covered_until=NOW - 3600)

    assert all(r.cold for r in plan_requests(NOW, stale, stale))


def test_nothing_is_planned_while_backing_off() -> None:
    waiting = FeedState(next_attempt_at=NOW + 30)

    assert plan_requests(NOW, waiting, waiting) == []


def test_truncated_arrivals_cover_up_to_the_last_landing() -> None:
    [request, *_] = plan_requests(NOW, FeedState(), FeedState())
    landings = [NOW + 5 * MINUTE, NOW + 25 * MINUTE]

    assert next_coverage(request, landings, True, None, NOW) == NOW + 25 * MINUTE


def test_truncated_arrivals_never_cover_past_the_requested_window() -> None:
    """One odd row far in the future must not leave the arrivals board stale for hours."""
    [request, *_] = plan_requests(NOW, FeedState(), FeedState())
    landings = [NOW + 10 * MINUTE, NOW + 240 * MINUTE]

    assert next_coverage(request, landings, True, None, NOW) == request.end


def test_truncated_arrivals_without_estimates_are_credited_half_the_window() -> None:
    [request, *_] = plan_requests(NOW, FeedState(), FeedState())

    covered = next_coverage(request, [], True, None, NOW)

    assert covered == request.start + (request.end - request.start) / 2


def test_truncated_departures_are_credited_half_the_window() -> None:
    departures = FeedState(covered_until=NOW + 5 * MINUTE)
    [request] = plan_requests(NOW, FeedState(covered_until=NOW + 60 * MINUTE), departures)

    covered = next_coverage(request, [], True, departures.covered_until, NOW)

    assert covered == request.start + (request.end - request.start) / 2


def test_complete_answer_covers_the_whole_window() -> None:
    [request, *_] = plan_requests(NOW, FeedState(), FeedState())

    assert next_coverage(request, [], False, None, NOW) == request.end


def test_cold_fetch_always_leaves_some_coverage_ahead() -> None:
    """Otherwise a busy, truncated first page would be refetched every tick."""
    [request, *_] = plan_requests(NOW, FeedState(), FeedState())

    covered = next_coverage(request, [NOW - 10 * MINUTE], True, None, NOW)

    assert covered == NOW + COLD_MIN_COVERAGE


def test_warm_fetch_always_moves_coverage_a_full_step_forward() -> None:
    """A truncated page that ends before the old coverage still buys a step of quiet."""
    arrivals = FeedState(covered_until=NOW + 15 * MINUTE)
    [request] = plan_requests(NOW, arrivals, FeedState(covered_until=NOW + 60 * MINUTE))

    covered = next_coverage(request, [NOW + 12 * MINUTE], True, arrivals.covered_until, NOW)

    assert covered == arrivals.covered_until + MIN_COVERAGE_STEP
