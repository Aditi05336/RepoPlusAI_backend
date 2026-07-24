"""
app.py

Main Flask application for RepoPulse AI.

Responsibilities:
- Initialize Flask + CORS.
- Load configuration.
- Define API endpoints.
- Coordinate the workflow: fetch GitHub data -> run analytics ->
  run ML forecast -> generate AI summary -> return JSON.

This file contains NO business logic. It is a controller only — every
calculation and API call is delegated to the appropriate module.
"""

import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

import ai_summary
import analytics
import github_api
import ml_forecast
from cache import build_repo_cache_key, cache
from config import config
from auth.utils import jwt_required
from utils import GitHubAPIError, error_response, success_response

logging.basicConfig(level=logging.INFO if not config.DEBUG else logging.DEBUG)
logger = logging.getLogger("repopulse")


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": config.CORS_ORIGIN}})

    # Configure SQLAlchemy Database
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    from auth.models import db
    from auth.routes import auth_bp

    db.init_app(app)
    app.register_blueprint(auth_bp)

    # Automatically create database tables (e.g., User model) if missing
    with app.app_context():
        try:
            db.create_all()
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);"))
            db.session.commit()
            logger.info("Database tables initialized successfully in PostgreSQL.")
        except Exception as exc:
            db.session.rollback()
            logger.warning("Could not auto-create database tables on startup: %s", exc)

    # Log any configuration warnings (missing tokens/keys) at startup.
    for warning in config.validate():
        logger.warning(warning)

    register_routes(app)
    return app


def register_routes(app: Flask) -> None:
    @app.after_request
    def after_request_callback(response):
        if response.mimetype == "application/json":
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    @app.route("/", methods=["GET"])

    def home():
        """Root endpoint returning service status and available routes."""
        body, status = success_response({
            "service": "RepoPulse AI Backend API",
            "status": "running",
            "endpoints": {
                "health": "GET /api/health",
                "analyze": "POST /api/analyze"
            }
        })
        return jsonify(body), status

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Simple liveness check for deployment platforms (Render, etc.)."""
        body, status = success_response({"status": "ok"})
        return jsonify(body), status

    @app.route("/api/analyze", methods=["POST"])
    @jwt_required
    def analyze_repository():
        """
        Full analysis workflow:

        Receive Request
              -> Fetch GitHub Data
              -> Run Analytics
              -> Run ML Forecast
              -> Generate AI Summary
              -> Return JSON Response
        """
        payload = request.get_json(silent=True) or {}
        owner = (payload.get("owner") or "").strip()
        repo = (payload.get("repository") or payload.get("repo") or "").strip()

        if not owner or not repo:
            body, status = error_response(
                "Both 'owner' and 'repository' are required fields.", status_code=422
            )
            return jsonify(body), status

        force_refresh = request.args.get("nocache", "").lower() in ("true", "1") or payload.get("nocache")
        cache_key = build_repo_cache_key(owner, repo)
        if not force_refresh:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                body, status = success_response(cached_result)
                body["cached"] = True
                return jsonify(body), status

        # 1. Fetch GitHub Data
        try:
            repo_data = github_api.fetch_full_repository_data(owner, repo)
        except GitHubAPIError as exc:
            status_code = exc.status_code or 502
            body, status = error_response(str(exc), status_code=status_code)
            return jsonify(body), status
        except Exception:
            logger.exception("Unexpected error fetching GitHub data for %s/%s", owner, repo)
            body, status = error_response(
                "Unexpected error while fetching repository data.", status_code=502
            )
            return jsonify(body), status

        # 2. Run Analytics
        try:
            scores = analytics.run_full_analysis(repo_data)
        except Exception:
            logger.exception("Analytics failure for %s/%s", owner, repo)
            body, status = error_response(
                "Failed to compute repository analytics.", status_code=500
            )
            return jsonify(body), status

        # 3. Run ML Forecast
        try:
            forecast = ml_forecast.predict_commit_trend(repo_data.get("commits", []))
        except Exception:
            logger.exception("ML forecast failure for %s/%s", owner, repo)
            forecast = {
                "predicted_next_week_commits": 0,
                "trend": "insufficient_data",
                "method": "fallback",
                "weekly_commit_history": [],
            }

        # 4. Generate AI Summary (Groq receives ONLY computed metrics, never raw data)
        metrics_for_ai = {
            "repo_full_name": repo_data["overview"].get("full_name", f"{owner}/{repo}"),
            **scores,
            "forecast_trend": forecast["trend"],
            "predicted_next_week_commits": forecast["predicted_next_week_commits"],
        }

        try:
            ai_insights = ai_summary.generate_ai_summary(metrics_for_ai)
        except Exception:
            logger.exception("AI summary failure for %s/%s", owner, repo)
            ai_insights = ai_summary._fallback_summary(metrics_for_ai)

        # 5. Assemble final response
        result = {
            "repository": repo_data["overview"],
            "scores": scores,
            "forecast": forecast,
            "contributors": repo_data.get("contributors", []),
            "languages": repo_data.get("languages", {}),
            "ai_insights": ai_insights,
        }

        cache.set(cache_key, result)

        body, status = success_response(result)
        body["cached"] = False
        return jsonify(body), status

    @app.errorhandler(404)
    def not_found(_error):
        body, status = error_response("Endpoint not found.", status_code=404)
        return jsonify(body), status

    @app.errorhandler(500)
    def internal_error(_error):
        body, status = error_response("Internal server error.", status_code=500)
        return jsonify(body), status


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)