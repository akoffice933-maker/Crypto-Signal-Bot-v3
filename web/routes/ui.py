from fastapi import APIRouter

from web.dashboard import dashboard

router = APIRouter(tags=["ui"])


router.add_api_route("/dashboard", dashboard, methods=["GET"])
