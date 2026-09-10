from fastapi.testclient import TestClient

from liftcam import __version__
from liftcam.api.main import app


def test_health_reports_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
