from app.routes.dashboard import _row
from app.utils import maturity_level

# The one shared banding: <2 Beginner, <3 Exploring, <4 Practitioner, else Leader.
EXPECTED = {
    1.4: "Beginner",
    1.5: "Beginner",
    2.0: "Exploring",
    2.5: "Exploring",
    3.0: "Practitioner",
    3.5: "Practitioner",
    4.0: "Leader",
}


class _Response:
    def __init__(self, score):
        self.score = score


def test_report_and_dashboard_use_the_same_maturity_bands():
    for average, expected in EXPECTED.items():
        report_level = maturity_level(average)
        dashboard = _row("Team", 1, [("member", [_Response(average)])], False)
        assert report_level == expected
        assert dashboard["level"] == report_level
