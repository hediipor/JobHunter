"""Self-check for POST /jobs/{id}/mark-applied: toggles is_applied, creates
exactly one Application row, and doesn't clobber a real pipeline status."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Application, Base, Job
from routes.jobs import mark_applied


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def demo():
    db = _session()
    job = Job(url="u1", title="Backend Engineer", status="new")
    db.add(job)
    db.commit()

    # mark applied: is_applied flips on, status -> applied, one Application row appears
    mark_applied(job.id, db)
    db.refresh(job)
    assert job.is_applied is True
    assert job.status == "applied"
    apps = db.query(Application).filter(Application.job_id == job.id).all()
    assert len(apps) == 1 and apps[0].response_status == "pending"

    # calling it again (misclick / re-applying) doesn't duplicate the Application row
    mark_applied(job.id, db)
    db.refresh(job)
    assert job.is_applied is False
    assert job.status == "new"  # reverted since nothing else had touched it
    assert db.query(Application).filter(Application.job_id == job.id).count() == 1

    # if the pipeline has since moved on (interview), unmarking shouldn't reset that
    mark_applied(job.id, db)  # back on: applied
    job.status = "interview"
    db.commit()
    mark_applied(job.id, db)  # unmark
    db.refresh(job)
    assert job.is_applied is False
    assert job.status == "interview"  # left alone, not "new"

    print("ok")


if __name__ == "__main__":
    demo()
