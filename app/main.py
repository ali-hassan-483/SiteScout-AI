"""SiteScout AI - application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.database import db, init_db
from app.security import create_session_token, read_session_token, verify_password

templates = Jinja2Templates(directory=str(config.BASE_DIR / "app" / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SiteScout AI",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def current_user_id(request: Request):
    token = request.cookies.get(config.SESSION_COOKIE)
    if not token:
        return None
    return read_session_token(token)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    with db() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid username or password"}, status_code=401
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        config.SESSION_COOKIE,
        create_session_token(row["id"]),
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=False,  # becomes True once the dashboard is served over HTTPS
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(config.SESSION_COOKIE)
    return response


@app.get("/")
def home(request: Request):
    if current_user_id(request) is None:
        return RedirectResponse("/login", status_code=303)
    return {"app": "SiteScout AI", "stage": "2.5 - logged in"}
