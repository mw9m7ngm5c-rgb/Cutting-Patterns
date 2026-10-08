"""SQLite tables. They follow the Simsaw schema closely so .mdb datasets import without loss.

Every input table hangs off a dataset. A batch run copies the inputs it used into ``Run.snapshot``
and stores its own results, so reports stay valid after the inputs change.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def _ds() -> Mapped[int]:
    return mapped_column(ForeignKey("dataset.id", ondelete="CASCADE"), index=True)


class Dataset(Base):
    __tablename__ = "dataset"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(200), default="")   # e.g. the .mdb file it came from
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ------------------------------------------------------------------ logs

class LogGrade(Base):
    __tablename__ = "log_grade"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    no: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(100))


class BoardGrade(Base):
    __tablename__ = "board_grade"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    no: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(100))


class LogClass(Base):
    __tablename__ = "log_class"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    no: Mapped[int] = mapped_column(Integer)
    min_diameter_cm: Mapped[float] = mapped_column(Float)
    max_diameter_cm: Mapped[float] = mapped_column(Float)
    min_length_m: Mapped[float] = mapped_column(Float, default=0.0)
    max_length_m: Mapped[float] = mapped_column(Float, default=99.0)
    length_incr_m: Mapped[float] = mapped_column(Float, default=0.3)
    min_taper: Mapped[float] = mapped_column(Float, default=0.0)        # mm/m
    max_taper: Mapped[float] = mapped_column(Float, default=999.0)
    min_sweep: Mapped[float] = mapped_column(Float, default=0.0)        # mm/m
    max_sweep: Mapped[float] = mapped_column(Float, default=999.0)
    min_ovality: Mapped[float] = mapped_column(Float, default=0.0)
    max_ovality: Mapped[float] = mapped_column(Float, default=9.0)
    min_defect_core: Mapped[float] = mapped_column(Float, default=0.0)  # % of SED
    max_defect_core: Mapped[float] = mapped_column(Float, default=100.0)
    log_price: Mapped[float] = mapped_column(Float, default=0.0)        # R/m3
    log_price_placeholder: Mapped[bool] = mapped_column(Boolean, default=False)
    grades: Mapped[list["LogGrade"]] = relationship(secondary="log_class_grade", lazy="selectin")


class LogClassGrade(Base):
    """Log grades a class accepts. None listed means every grade."""
    __tablename__ = "log_class_grade"
    log_class_id: Mapped[int] = mapped_column(ForeignKey("log_class.id", ondelete="CASCADE"), primary_key=True)
    log_grade_id: Mapped[int] = mapped_column(ForeignKey("log_grade.id", ondelete="CASCADE"), primary_key=True)


class Log(Base):
    __tablename__ = "log"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    log_no: Mapped[int] = mapped_column(Integer)
    sed_cm: Mapped[float] = mapped_column(Float)
    length_m: Mapped[float] = mapped_column(Float)
    taper: Mapped[float] = mapped_column(Float, default=0.0)            # mm/m
    sweep_mm: Mapped[float] = mapped_column(Float, default=0.0)         # total, mm (not mm/m)
    ovality: Mapped[float] = mapped_column(Float, default=1.0)
    defect_core_cm: Mapped[float] = mapped_column(Float, default=0.0)   # cm (not %)
    log_grade_id: Mapped[int | None] = mapped_column(ForeignKey("log_grade.id", ondelete="SET NULL"), nullable=True)


class LogGenerator(Base):
    """Last-used log generator settings, one row per dataset. Ranges in class-limit units."""
    __tablename__ = "log_generator"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    no_of_logs: Mapped[int] = mapped_column(Integer, default=100)
    fixed_seed: Mapped[bool] = mapped_column(Boolean, default=True)
    seed: Mapped[int] = mapped_column(Integer, default=1)
    min_diameter: Mapped[float] = mapped_column(Float, default=18.0)
    max_diameter: Mapped[float] = mapped_column(Float, default=40.0)
    diameter_distr: Mapped[int] = mapped_column(Integer, default=0)
    min_length: Mapped[float] = mapped_column(Float, default=2.4)
    max_length: Mapped[float] = mapped_column(Float, default=3.0)
    length_incr: Mapped[float] = mapped_column(Float, default=0.3)
    length_distr: Mapped[int] = mapped_column(Integer, default=0)
    min_taper: Mapped[float] = mapped_column(Float, default=8.0)
    max_taper: Mapped[float] = mapped_column(Float, default=11.0)
    taper_distr: Mapped[int] = mapped_column(Integer, default=2)
    min_sweep: Mapped[float] = mapped_column(Float, default=0.0)
    max_sweep: Mapped[float] = mapped_column(Float, default=15.0)
    sweep_distr: Mapped[int] = mapped_column(Integer, default=2)
    min_ovality: Mapped[float] = mapped_column(Float, default=0.95)
    max_ovality: Mapped[float] = mapped_column(Float, default=1.05)
    ovality_distr: Mapped[int] = mapped_column(Integer, default=2)
    min_defect_core: Mapped[float] = mapped_column(Float, default=0.0)
    max_defect_core: Mapped[float] = mapped_column(Float, default=0.0)
    defect_core_distr: Mapped[int] = mapped_column(Integer, default=2)
    log_grade_id: Mapped[int | None] = mapped_column(ForeignKey("log_grade.id", ondelete="SET NULL"), nullable=True)


# ------------------------------------------------------------------ products

class Thickness(Base):
    __tablename__ = "thickness"
    __table_args__ = (UniqueConstraint("dataset_id", "dry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    dry: Mapped[float] = mapped_column(Float)
    wet: Mapped[float] = mapped_column(Float)


class Width(Base):
    __tablename__ = "width"
    __table_args__ = (UniqueConstraint("dataset_id", "dry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    dry: Mapped[float] = mapped_column(Float)
    wet: Mapped[float] = mapped_column(Float)


class LengthClass(Base):
    __tablename__ = "length_class"
    __table_args__ = (UniqueConstraint("dataset_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    name: Mapped[str] = mapped_column(String(100))
    min_m: Mapped[float] = mapped_column(Float)
    max_m: Mapped[float] = mapped_column(Float)
    incr_m: Mapped[float] = mapped_column(Float)


class Combination(Base):
    """Thickness x width x length class x board grade: whether it is a product and its price."""
    __tablename__ = "combination"
    __table_args__ = (UniqueConstraint("thickness_id", "width_id", "length_class_id", "board_grade_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    thickness_id: Mapped[int] = mapped_column(ForeignKey("thickness.id", ondelete="CASCADE"))
    width_id: Mapped[int] = mapped_column(ForeignKey("width.id", ondelete="CASCADE"))
    length_class_id: Mapped[int] = mapped_column(ForeignKey("length_class.id", ondelete="CASCADE"))
    board_grade_id: Mapped[int] = mapped_column(ForeignKey("board_grade.id", ondelete="CASCADE"))
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)            # R/m3 dry
    price_placeholder: Mapped[bool] = mapped_column(Boolean, default=False)


class WaneRule(Base):
    __tablename__ = "wane_rule"
    __table_args__ = (UniqueConstraint("thickness_id", "width_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    thickness_id: Mapped[int] = mapped_column(ForeignKey("thickness.id", ondelete="CASCADE"))
    width_id: Mapped[int] = mapped_column(ForeignKey("width.id", ondelete="CASCADE"))
    thickness_pct: Mapped[float] = mapped_column(Float, default=0.0)
    width_pct: Mapped[float] = mapped_column(Float, default=0.0)
    length_wane: Mapped[float] = mapped_column(Float, default=0.0)
    length_wane_type: Mapped[int] = mapped_column(Integer, default=0)


class CentreBoard(Base):
    __tablename__ = "centre_board"
    __table_args__ = (UniqueConstraint("thickness_id", "width_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    thickness_id: Mapped[int] = mapped_column(ForeignKey("thickness.id", ondelete="CASCADE"))
    width_id: Mapped[int] = mapped_column(ForeignKey("width.id", ondelete="CASCADE"))


class GradeOutput(Base):
    """Probability (%) of a board grade, by the share of the board's cross-section in the defect core."""
    __tablename__ = "grade_output"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    thickness_id: Mapped[int] = mapped_column(ForeignKey("thickness.id", ondelete="CASCADE"))
    width_id: Mapped[int] = mapped_column(ForeignKey("width.id", ondelete="CASCADE"))
    log_grade_id: Mapped[int] = mapped_column(ForeignKey("log_grade.id", ondelete="CASCADE"))
    board_grade_id: Mapped[int] = mapped_column(ForeignKey("board_grade.id", ondelete="CASCADE"))
    p_zero: Mapped[float] = mapped_column(Float, default=100.0)          # no core in the board
    p_fifty: Mapped[float] = mapped_column(Float, default=100.0)         # 1 to 50 %
    p_ninety_nine: Mapped[float] = mapped_column(Float, default=100.0)   # 51 to 99 %
    p_hundred: Mapped[float] = mapped_column(Float, default=100.0)       # all core


# ------------------------------------------------------------------ machines and patterns

class ProductionLine(Base):
    __tablename__ = "production_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    no: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(100))
    saw_type: Mapped[int] = mapped_column(Integer, default=0)
    primary_machine: Mapped[str] = mapped_column(String(50), default="")
    secondary_machine: Mapped[str] = mapped_column(String(50), default="")
    primary_kerf: Mapped[float] = mapped_column(Float, default=3.0)
    primary_outside_kerf: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_outside_blades: Mapped[int] = mapped_column(Integer, default=0)
    secondary_kerf: Mapped[float] = mapped_column(Float, default=3.0)
    secondary_outside_kerf: Mapped[float | None] = mapped_column(Float, nullable=True)
    secondary_outside_blades: Mapped[int] = mapped_column(Integer, default=0)
    primary_resaw: Mapped[bool] = mapped_column(Boolean, default=False)
    primary_resaw_kerf: Mapped[float] = mapped_column(Float, default=5.0)
    secondary_resaw: Mapped[bool] = mapped_column(Boolean, default=False)
    secondary_resaw_kerf: Mapped[float] = mapped_column(Float, default=5.0)
    cant_guiding: Mapped[int] = mapped_column(Integer, default=0)
    max_sweep: Mapped[float] = mapped_column(Float, default=999.0)
    log_rotation_deg: Mapped[float] = mapped_column(Float, default=0.0)
    log_misalignment_mm: Mapped[float] = mapped_column(Float, default=0.0)
    primary_offset_mm: Mapped[float] = mapped_column(Float, default=0.0)
    cant_misalignment_mm: Mapped[float] = mapped_column(Float, default=0.0)
    secondary_offset_mm: Mapped[float] = mapped_column(Float, default=0.0)
    edging_objective: Mapped[int] = mapped_column(Integer, default=0)
    edger_blades: Mapped[int] = mapped_column(Integer, default=2)
    edger_kerf: Mapped[float] = mapped_column(Float, default=5.0)
    second_board_width: Mapped[str] = mapped_column(String(20), default="Best")
    max_boards_per_flitch: Mapped[int] = mapped_column(Integer, default=0)
    kerfs_placeholder: Mapped[bool] = mapped_column(Boolean, default=False)


class SawPattern(Base):
    __tablename__ = "saw_pattern"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    line_id: Mapped[int] = mapped_column(ForeignKey("production_line.id", ondelete="CASCADE"))
    log_class_id: Mapped[int] = mapped_column(ForeignKey("log_class.id", ondelete="CASCADE"))
    pattern_no: Mapped[int] = mapped_column(Integer, default=1)
    primary: Mapped[str] = mapped_column(String(200), default="")
    secondary: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")   # manual | imported | generated


class DatasetSettings(Base):
    __tablename__ = "dataset_settings"
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id", ondelete="CASCADE"), primary_key=True)
    use_nominal_diameter: Mapped[bool] = mapped_column(Boolean, default=True)
    nominal_diameter: Mapped[int] = mapped_column(Integer, default=0)
    use_nominal_length: Mapped[bool] = mapped_column(Boolean, default=True)
    nominal_length_incr_m: Mapped[float] = mapped_column(Float, default=0.3)
    use_nominal_taper: Mapped[bool] = mapped_column(Boolean, default=True)
    nominal_taper_mm_per_m: Mapped[float] = mapped_column(Float, default=10.0)
    disc_separation_cm: Mapped[float] = mapped_column(Float, default=5.0)
    points_per_disc: Mapped[int] = mapped_column(Integer, default=64)
    discretised: Mapped[bool] = mapped_column(Boolean, default=False)
    seed: Mapped[int] = mapped_column(Integer, default=1)
    chip_price: Mapped[float] = mapped_column(Float, default=0.0)
    sawdust_price: Mapped[float] = mapped_column(Float, default=0.0)
    pct_fines: Mapped[float] = mapped_column(Float, default=0.0)
    arris_small_end: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    real_logs: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    diameter_variation: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")   # % of radius
    taper_variation: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")      # % of diameter
    sweep_variation: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")      # mm
    ovality_variation: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")    # % of ovality


# ------------------------------------------------------------------ batch runs

class Run(Base):
    __tablename__ = "run"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    source: Mapped[str] = mapped_column(String(20), default="app")      # app | simsaw (imported results)
    status: Mapped[str] = mapped_column(String(20), default="queued")   # queued running done cancelled failed
    progress: Mapped[int] = mapped_column(Integer, default=0)           # logs sawn so far
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[str] = mapped_column(Text, default="{}")           # every input the run used (JSON)


class RunPattern(Base):
    __tablename__ = "run_pattern"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    line_name: Mapped[str] = mapped_column(String(100))
    class_no: Mapped[int] = mapped_column(Integer)
    pattern_no: Mapped[int] = mapped_column(Integer)
    primary: Mapped[str] = mapped_column(String(200))
    secondary: Mapped[str] = mapped_column(String(200))
    diameter_range: Mapped[str] = mapped_column(String(50), default="")
    log_price: Mapped[float] = mapped_column(Float, default=0.0)
    chip_price: Mapped[float] = mapped_column(Float, default=0.0)
    sawdust_price: Mapped[float] = mapped_column(Float, default=0.0)
    pct_fines: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")


class RunLogResult(Base):
    __tablename__ = "run_log_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_pattern_id: Mapped[int] = mapped_column(ForeignKey("run_pattern.id", ondelete="CASCADE"), index=True)
    log_no: Mapped[int] = mapped_column(Integer)
    sed_cm: Mapped[float] = mapped_column(Float, default=0.0)
    length_m: Mapped[float] = mapped_column(Float, default=0.0)
    log_volume: Mapped[float] = mapped_column(Float)
    dry_volume: Mapped[float] = mapped_column(Float)
    wet_volume: Mapped[float] = mapped_column(Float)
    value: Mapped[float] = mapped_column(Float)
    sawdust_volume: Mapped[float] = mapped_column(Float)
    chip_volume: Mapped[float] = mapped_column(Float)
    boards: Mapped[int] = mapped_column(Integer)


class RunBoardResult(Base):
    __tablename__ = "run_board_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_pattern_id: Mapped[int] = mapped_column(ForeignKey("run_pattern.id", ondelete="CASCADE"), index=True)
    log_no: Mapped[int] = mapped_column(Integer)
    board_type: Mapped[int] = mapped_column(Integer)
    board_no: Mapped[int] = mapped_column(Integer)
    thickness: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    length_m: Mapped[float] = mapped_column(Float)
    left: Mapped[float] = mapped_column(Float)
    right: Mapped[float] = mapped_column(Float)
    bottom: Mapped[float] = mapped_column(Float)
    top: Mapped[float] = mapped_column(Float)
    front_m: Mapped[float] = mapped_column(Float)
    back_m: Mapped[float] = mapped_column(Float)
    resawn: Mapped[bool] = mapped_column(Boolean, default=False)
    resaw_position: Mapped[float] = mapped_column(Float, default=0.0)
    edged: Mapped[bool] = mapped_column(Boolean, default=False)
    piece: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    core_share: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    grade: Mapped[str] = mapped_column(String(100), default="")
    dry_volume: Mapped[float] = mapped_column(Float)
    wet_volume: Mapped[float] = mapped_column(Float)
    value: Mapped[float] = mapped_column(Float)


# ------------------------------------------------------------------ pattern generator

class GeneratorJob(Base):
    """One generator search: for a class / diameter ("class") or across diameters ("chart")."""
    __tablename__ = "generator_job"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = _ds()
    kind: Mapped[str] = mapped_column(String(10))                      # class | chart
    title: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    params: Mapped[str] = mapped_column(Text, default="{}")             # the form, as JSON
    snapshot: Mapped[str] = mapped_column(Text, default="{}")           # engine inputs, as for a run
    status: Mapped[str] = mapped_column(String(20), default="queued")   # queued running done cancelled failed
    stage: Mapped[str] = mapped_column(String(100), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")               # JSON
