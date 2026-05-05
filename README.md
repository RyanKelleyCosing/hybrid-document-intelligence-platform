# Security Posture Platform (Public Demo)

This repository is a public-safe, interview-ready demonstration of the Hybrid
Document Intelligence architecture. It shows how the system is designed,
implemented, and validated without publishing the private operator platform,
deployment contracts, or tenant-bearing runtime configuration.

## Contact

For a demo walkthrough or interview discussion:

- Email: ryankelley1013@gmail.com

## What This Public Repo Includes

- `security-posture-site/`: Frontend package for the public security experience
- `security-posture-api/`: Standalone Azure Functions package for public-safe
	telemetry and request-context routes
- `.github/workflows/validate.yml`: CI validation for both packages

## What Is Intentionally Excluded

- Private admin/operator review workbench and protected queue routes
- Private deployment scripts, resource-specific infrastructure wiring, and
	secret-bearing environment values
- End-to-end composition required to run the full production system

The goal is to provide clear technical evidence and representative code shape,
not a one-command clone of the private operational platform.

## Representative Snippets

### Frontend Pattern (public telemetry presentation)

```tsx
type TelemetryPanelProps = {
	label: string;
	value: string;
	detail: string;
};

export function TelemetryPanel({ label, value, detail }: TelemetryPanelProps) {
	return (
		<section aria-label={label}>
			<h3>{label}</h3>
			<p>{value}</p>
			<small>{detail}</small>
		</section>
	);
}
```

### Backend Pattern (public-safe API response)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicRequestSummary:
		route: str
		region: str
		likely_bot: bool


def build_public_summary(route: str, region: str, score: float) -> PublicRequestSummary:
		return PublicRequestSummary(
				route=route,
				region=region,
				likely_bot=score >= 0.7,
		)
```

These snippets demonstrate style and structure only; they are not the full
private implementation.

## Local Validation

```powershell
Set-Location security-posture-site
npm install
npm test
npm run build

Set-Location ..\security-posture-api
pip install -r requirements.txt
pip install -e .[dev]
pytest tests/unit
```
