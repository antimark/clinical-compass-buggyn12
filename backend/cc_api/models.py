from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))
    specialty: Mapped[str | None] = mapped_column(String(50), nullable=True)
    organization_id: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_subject: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    profile_json: Mapped[str] = mapped_column(Text, default='{}', server_default='{}')
    profile_revision: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    profile_photo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Patient(Base):
    __tablename__ = 'patients'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    diagnosis_label: Mapped[str] = mapped_column(String(150))
    medication_label: Mapped[str] = mapped_column(String(150))
    severity_label: Mapped[str] = mapped_column(String(100))
    trend: Mapped[str] = mapped_column(String(30))
    last_activity_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DoctorPatientLink(Base):
    __tablename__ = 'doctor_patient_links'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    categories: Mapped[str] = mapped_column(String(300))


class Checkin(Base):
    __tablename__ = 'checkins'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    mood_score: Mapped[int] = mapped_column(Integer)
    comparison: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(2000))
    recorded_at: Mapped[str] = mapped_column(String(40))


class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assigned_doctor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    patient_id: Mapped[str] = mapped_column(ForeignKey('patients.id'))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[str] = mapped_column(String(40))
    acknowledged_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(50))
