"""SiteScout AI - application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import config, leads
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


def guard(request: Request):
    """Return a redirect response if not logged in, else None."""
    if current_user_id(request) is None:
        return RedirectResponse("/login", status_code=303)
    return None


def render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def not_found():
    return HTMLResponse("Lead not found", status_code=404)


def due_followups():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, name, city, followup_date, status FROM leads "
            "WHERE followup_date IS NOT NULL AND followup_date != '' "
            "AND followup_date <= date('now') "
            "AND status NOT IN ('won', 'lost', 'inactive') AND do_not_contact = 0 "
            "ORDER BY followup_date LIMIT 20"
        ).fetchall()
    return [dict(r) for r in rows]


def form_context(lead, errors, heading, action):
    return dict(
        lead=lead, errors=errors, heading=heading, action=action,
        statuses=leads.STATUSES, priorities=leads.PRIORITIES,
        website_statuses=leads.WEBSITE_STATUSES,
    )


def read_lead_form(form) -> dict:
    data = {k: form.get(k) for k in leads.EDITABLE_FIELDS if k in form}
    for key in ("status", "priority", "website_status"):
        if not data.get(key):
            data.pop(key, None)
    return data


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html", error=None)


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    with db() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return render(request, "login.html", 401, error="Invalid username or password")
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


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if (r := guard(request)):
        return r
    return render(request, "index.html", counts=leads.dashboard_counts(), due=due_followups())


@app.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, search: str = "", status: str = "",
               priority: str = "", website_status: str = ""):
    if (r := guard(request)):
        return r
    rows = leads.list_leads(search.strip(), status, priority, website_status)
    return render(
        request, "leads_list.html", leads=rows, search=search, status=status,
        priority=priority, website_status=website_status,
        statuses=leads.STATUSES, priorities=leads.PRIORITIES,
        website_statuses=leads.WEBSITE_STATUSES,
    )


@app.get("/leads/new", response_class=HTMLResponse)
def new_lead_page(request: Request):
    if (r := guard(request)):
        return r
    return render(request, "lead_form.html", **form_context({}, [], "Add lead", "/leads/new"))


@app.post("/leads/new")
async def new_lead_submit(request: Request):
    if (r := guard(request)):
        return r
    data = read_lead_form(await request.form())
    errors = leads.validate(data)
    if errors:
        return render(request, "lead_form.html", 400,
                      **form_context(data, errors, "Add lead", "/leads/new"))
    lead_id = leads.create_lead(data)
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.get("/leads/export.csv")
def export_csv(request: Request):
    if (r := guard(request)):
        return r
    return Response(
        leads.export_csv(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sitescout_leads.csv"},
    )


@app.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(request: Request, lead_id: int):
    if (r := guard(request)):
        return r
    lead = leads.get_lead(lead_id)
    if lead is None:
        return not_found()
    return render(request, "lead_detail.html", lead=lead,
                  notes=leads.get_notes(lead_id), events=leads.get_events(lead_id))


@app.get("/leads/{lead_id}/edit", response_class=HTMLResponse)
def edit_lead_page(request: Request, lead_id: int):
    if (r := guard(request)):
        return r
    lead = leads.get_lead(lead_id)
    if lead is None:
        return not_found()
    return render(request, "lead_form.html",
                  **form_context(lead, [], "Edit lead", f"/leads/{lead_id}/edit"))


@app.post("/leads/{lead_id}/edit")
async def edit_lead_submit(request: Request, lead_id: int):
    if (r := guard(request)):
        return r
    if leads.get_lead(lead_id) is None:
        return not_found()
    data = read_lead_form(await request.form())
    errors = leads.validate(data)
    if errors:
        return render(request, "lead_form.html", 400,
                      **form_context(data, errors, "Edit lead", f"/leads/{lead_id}/edit"))
    leads.update_lead(lead_id, data)
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/notes")
def add_note(request: Request, lead_id: int, note: str = Form(...)):
    if (r := guard(request)):
        return r
    if leads.get_lead(lead_id) is None:
        return not_found()
    leads.add_note(lead_id, note)
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/dnc")
def do_not_contact(request: Request, lead_id: int, flag: str = Form("0")):
    if (r := guard(request)):
        return r
    if leads.get_lead(lead_id) is None:
        return not_found()
    leads.set_do_not_contact(lead_id, flag == "1")
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@app.post("/leads/{lead_id}/delete")
def delete_lead(request: Request, lead_id: int):
    if (r := guard(request)):
        return r
    leads.delete_lead(lead_id)
    return RedirectResponse("/leads", status_code=303)

from app.routes_discovery import router as discovery_router  # noqa: E402
app.include_router(discovery_router)
