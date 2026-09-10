from fastapi import FastAPI

from liftcam import __version__

app = FastAPI(title="LiftCam API", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
