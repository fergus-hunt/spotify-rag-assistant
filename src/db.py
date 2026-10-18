import logging
import os

import dotenv
import psycopg2  # noqa: F401
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

dotenv.load_dotenv()
logger = logging.getLogger(__name__)


DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PORT = os.environ.get("DB_PORT", 5432)

database_url = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(database_url)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Import all models at module level so Base.metadata knows about them
# and mappers compile correctly whenever db is imported.
import src.models.artist  # noqa: F401
import src.models.audio_features  # noqa: F401
import src.models.embedding  # noqa: F401
import src.models.played_history  # noqa: F401
import src.models.track  # noqa: F401


def init_db(engine):
    """Initializes schema tables, materialized views, and indexes."""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

        Base.metadata.create_all(engine)

        mat_view_sql = """
DROP VIEW IF EXISTS v_listening_history CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_listening_history CASCADE;

CREATE MATERIALIZED VIEW mv_listening_history AS
SELECT 
    ph.id AS history_id,
    ph.played_at,
    ph.played_time,
    t.uri AS track_uri,
    t.title AS track_title,
    t.album_name,
    t.release_date,
    t.popularity,
    ROUND(t.duration_ms / 1000.0, 1) AS duration_seconds,
    ROUND(ph.played_time / 1000.0, 3) AS played_time_seconds,
    COALESCE(string_agg(DISTINCT a.name, ', '), 'Unknown Artist') AS artist_names,
    (SELECT string_agg(DISTINCT g, ', ')
     FROM track_artists ta_g
     JOIN artists a_g ON ta_g.artist_uri = a_g.uri,
     LATERAL unnest(a_g.genres) AS g
     WHERE ta_g.track_uri = t.uri
    ) AS artist_genres,
    af.tempo,
    af.energy,
    af.danceability,
    af.valence
FROM played_history ph
JOIN tracks t ON ph.track_uri = t.uri
LEFT JOIN track_artists ta ON t.uri = ta.track_uri
LEFT JOIN artists a ON ta.artist_uri = a.uri
LEFT JOIN audio_features af ON t.uri = af.track_uri
GROUP BY
    ph.id, ph.played_at, t.uri, t.title, t.album_name, t.release_date,
    t.popularity, t.duration_ms, af.tempo, af.energy, af.danceability,
    af.valence;

-- Compound and GIN Trigram indexes on Materialized View for instant search
CREATE INDEX IF NOT EXISTS idx_mv_played_at ON mv_listening_history (played_at DESC);
CREATE INDEX IF NOT EXISTS idx_mv_track_uri ON mv_listening_history (track_uri);
CREATE INDEX IF NOT EXISTS idx_mv_track_title_trgm
    ON mv_listening_history USING gin (track_title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_mv_artist_names_trgm
    ON mv_listening_history USING gin (artist_names gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_mv_artist_genres_trgm
    ON mv_listening_history USING gin (artist_genres gin_trgm_ops);

-- Base table performance indexes
CREATE INDEX IF NOT EXISTS idx_ph_played_at ON played_history (played_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_track_uri ON played_history (track_uri);

-- Lightweight view interface over Materialized View for 100% backward compatibility
CREATE OR REPLACE VIEW v_listening_history AS SELECT * FROM mv_listening_history;
"""

        with engine.begin() as conn:
            conn.execute(text(mat_view_sql))

        logger.info(
            "Database schema, materialized views, and performance indexes initialized."
        )
    except Exception as e:
        logger.error(f"Failed to initialise database: {e}")
        raise e


def refresh_materialized_view(bind_engine=None):
    """Refreshes mv_listening_history concurrently if possible or standard."""
    target_engine = bind_engine or engine
    try:
        with target_engine.begin() as conn:
            conn.execute(text("REFRESH MATERIALIZED VIEW mv_listening_history;"))
        logger.info("Materialized view mv_listening_history refreshed successfully.")
    except Exception as e:
        logger.warning(f"Failed to refresh materialized view: {e}")
