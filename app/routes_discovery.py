"""SiteScout AI - discovery page routes."""
import threading

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.discovery import CATEGORIES, DiscoveryError, discover
from app.importer import import_leads
from app.security import read_session_token

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "app" / "templates"))
_busy = threading.Lock()


def _logged_in(request: Request) -> bool:
    token = request.cookies.get(config.SESSION_COOKIE)
    return bool(token) and read_session_token(token) is not None


def _page(request, form=None, result=None, error=None, status_code=200):
    return templates.TemplateResponse(
        request, "discovery.html",
        {"form": form or {}, "result": result, "error": error, "categories": list(CATEGORIES)},
        status_code=status_code,
    )


@router.get("/discover", response_class=HTMLResponse)
def discover_page(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    return _page(request, form={"category": "cafe"})


@router.post("/discover", response_class=HTMLResponse)
def discover_submit(
    request: Request,
    city: str = Form(...),
    country: str = Form(""),
    category: str = Form("cafe"),
    only_with_phone: str = Form(""),
    only_no_website: str = Form(""),
):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    city, country = city.strip(), country.strip()
    form = {"city": city, "country": country, "category": category,
            "only_with_phone": bool(only_with_phone), "only_no_website": bool(only_no_website)}
    if not city or len(city) > 100 or len(country) > 100:
        return _page(request, form, error="Please enter a valid city name.", status_code=400)
    if category not in CATEGORIES:
        return _page(request, form, error="Unknown category.", status_code=400)
    if not _busy.acquire(blocking=False):
        return _page(request, form, error="A discovery is already running. Please wait for it to finish.",
                     status_code=429)
    try:
        found, source = discover(city, country, category)
        counts = import_leads(found, bool(only_with_phone), bool(only_no_website))
    except DiscoveryError as exc:
        return _page(request, form, error=(
            "The map data servers are not reachable right now, so no search was done. "
            "This does NOT mean there are no businesses. Please try again later. "
            f"Details: {exc}"), status_code=503)
    finally:
        _busy.release()
    result = {"source": source, "total": len(found), **counts}
    return _page(request, form, result=result)
