import json
from ..models import InvestigationReport


class JSONReporter:
    """Exports investigation reports as formatted JSON."""

    def render(self, report: InvestigationReport) -> str:
        return report.model_dump_json(indent=2)
