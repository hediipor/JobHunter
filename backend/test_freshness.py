"""Self-check for fresh_jobs(): stale jobs hidden, latest scan + tracked jobs kept."""
import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from database import Base, Job, fresh_jobs


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def demo():
    db = _session()
    now = datetime.datetime.utcnow()
    old = now - datetime.timedelta(days=3)

    db.add_all([
        Job(url="u1", title="fresh", status="new", last_seen=now),
        Job(url="u2", title="also fresh", status="new", last_seen=now - datetime.timedelta(hours=2)),
        Job(url="u3", title="stale", status="new", last_seen=old),
        Job(url="u4", title="stale but saved", status="saved", last_seen=old),
        Job(url="u5", title="stale but applied", status="new", is_applied=True, last_seen=old),
    ])
    db.commit()

    urls = {j.url for j in fresh_jobs(db).all()}
    assert urls == {"u1", "u2", "u4", "u5"}, urls

    # empty DB: no crash, no filter
    db2 = _session()
    assert fresh_jobs(db2).all() == []
    print("ok")


if __name__ == "__main__":
    demo()
