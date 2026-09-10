from fastapi import FastAPI

from liftcam import __version__
from liftcam.api.routers import auth, users

app = FastAPI(title="LiftCam API", version=__version__)
app.include_router(auth.router)
app.include_router(users.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
