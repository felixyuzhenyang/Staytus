"""Synthetic records for tests only; startup never loads these fixtures."""
from datetime import date
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Account, PolicyChunk, PolicySource, PolicyVersion, Profile, RuleVersion


FIXTURE_PASSWORD = "staytus-test-password"


def seed_fixtures(db: Session):
    if db.scalar(select(Profile.id).limit(1)):
        return
    db.add_all([
        Profile(id="mei-lin", name="Mei Lin", status_type="F-1", program_start=date(2026, 8, 20), program_end=date(2027, 5, 15), graduation_date=date(2027, 5, 15), travel_date=date(2027, 1, 10), travel_signature_date=date(2026, 8, 22), nationality="Synthetic profile"),
        Profile(id="sam-rivera", name="Sam Rivera", status_type="J-1 student", program_start=date(2026, 8, 20), program_end=date(2027, 6, 30), graduation_date=date(2027, 6, 30), nationality="Synthetic profile"),
        Profile(id="amina-ali", name="Amina Ali", status_type="J-1 scholar", program_start=date(2026, 9, 1), program_end=date(2027, 8, 31), nationality="Synthetic profile"),
    ])
    sources = [
        PolicySource(id="penn-isss", title="Penn ISSS", url="https://global.upenn.edu/isss/", allowed_host="global.upenn.edu"),
        PolicySource(id="uscis", title="USCIS Students and Exchange Visitors", url="https://www.uscis.gov/working-in-the-united-states/students-and-exchange-visitors", allowed_host="www.uscis.gov"),
        PolicySource(id="study-in-states", title="DHS Study in the States", url="https://studyinthestates.dhs.gov/", allowed_host="studyinthestates.dhs.gov"),
    ]
    db.add_all(sources)
    db.flush()
    texts = [
        ("demo-extension", "penn-isss", "Program-extension planning", "DEMO FIXTURE: Contact your university's international adviser before the program end date on the I-20 or DS-2019 if additional time may be needed. The 60-day preparation buffer in this app is a fictional Staytus planning preference, not an official filing deadline. Verify current requirements at the official link.", ["F-1", "J-1 student", "J-1 scholar"]),
        ("demo-travel", "penn-isss", "Travel document review", "DEMO FIXTURE: Before international travel, review your passport, visa, I-20 or DS-2019, travel endorsement, and re-entry situation with ISSS. This prototype does not determine admissibility, travel eligibility, or legal status. The app's 30-day travel review is an internal reminder only.", ["F-1", "J-1 student", "J-1 scholar"]),
        ("demo-employment", "uscis", "Employment authorization questions", "DEMO FIXTURE: Employment authorization depends on individual circumstances and the applicable category. F-1 OPT and J-1 employment follow different procedures. Verify current official guidance and adviser instructions before work. This prototype does not calculate an OPT filing window.", ["F-1", "J-1 student", "J-1 scholar"]),
    ]
    for pid, source_id, title, text, visa_types in texts:
        version = PolicyVersion(id=pid, source_id=source_id, title=title, text=text, content_hash=sha256(text.encode()).hexdigest(), status="current_effective", reviewed=True, fixture=True, visa_types=visa_types)
        db.add(version)
        db.flush()
        db.add(PolicyChunk(policy_version_id=pid, text=text))
    db.add(RuleVersion(id="penn-planning-v1", version=1, preparation_days=60, policy_version_id="demo-extension", reviewed_by="demo-fixture"))
    for profile in db.scalars(select(Profile)):
        account = Account(id="account-" + profile.id, email=profile.id + "@example.invalid",
                          name=profile.name, password_hash=hash_password(FIXTURE_PASSWORD))
        db.add(account)
        db.flush()
        profile.account_id = account.id
        profile.email = account.email
        profile.synthetic = True
    db.commit()
