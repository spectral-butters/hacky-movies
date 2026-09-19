from fastapi import FastAPI

from backend.main import app as backend_app


app = FastAPI(
    title=backend_app.title,
    version=backend_app.version,
    lifespan=backend_app.router.lifespan_context,
)
app.state.database = backend_app.state.database
app.state.repository = backend_app.state.repository
app.include_router(backend_app.router)
