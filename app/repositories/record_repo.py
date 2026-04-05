from datetime import date
from decimal import Decimal
from dateutil.relativedelta import relativedelta

from sqlalchemy import select, func as sa_func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import Record, RecordType
from app.schemas.record import RecordCreate, RecordUpdate, AggregationPeriod


class RecordRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: RecordCreate, created_by: int) -> Record:
        record = Record(**data.model_dump(), created_by=created_by)
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def get_by_id(self, record_id: int) -> Record | None:
        return await self.db.get(Record, record_id)

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 50,
        type_filter: RecordType | None = None,
        category: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Record]:
        stmt = select(Record)
        if type_filter:
            stmt = stmt.where(Record.type == type_filter)
        if category:
            stmt = stmt.where(Record.category == category)
        if date_from:
            stmt = stmt.where(Record.date >= date_from)
        if date_to:
            stmt = stmt.where(Record.date <= date_to)
        stmt = stmt.order_by(Record.date.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, record: Record, data: RecordUpdate, updated_by: int) -> Record:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(record, key, value)
        record.updated_by = updated_by
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def delete(self, record: Record) -> None:
        await self.db.delete(record)
        await self.db.flush()

    # ── Dashboard helpers ──

    async def get_summary(self) -> dict:
        def _get_trend(current: Decimal, previous: Decimal) -> float:
            if previous == 0:
                return 100.0 if current > 0 else (0.0 if current == 0 else -100.0)
            return float((current - previous) / abs(previous) * 100)

        income = await self.db.execute(
            select(sa_func.coalesce(sa_func.sum(Record.amount), 0)).where(Record.type == RecordType.income)
        )
        expense = await self.db.execute(
            select(sa_func.coalesce(sa_func.sum(Record.amount), 0)).where(Record.type == RecordType.expense)
        )
        total_income = Decimal(str(income.scalar()))
        total_expense = Decimal(str(expense.scalar()))
        net_balance = total_income - total_expense

        today = date.today()
        current_month_start = today.replace(day=1)
        prev_month_start = current_month_start - relativedelta(months=1)

        async def get_period_sum(rec_type: RecordType, start_dt: date, end_dt: date | None) -> Decimal:
            stmt = select(sa_func.coalesce(sa_func.sum(Record.amount), 0)).where(Record.type == rec_type, Record.date >= start_dt)
            if end_dt:
                stmt = stmt.where(Record.date < end_dt)
            res = await self.db.execute(stmt)
            return Decimal(str(res.scalar()))

        cur_income = await get_period_sum(RecordType.income, current_month_start, None)
        cur_expense = await get_period_sum(RecordType.expense, current_month_start, None)
        prev_income = await get_period_sum(RecordType.income, prev_month_start, current_month_start)
        prev_expense = await get_period_sum(RecordType.expense, prev_month_start, current_month_start)

        cur_balance = cur_income - cur_expense
        prev_balance = prev_income - prev_expense

        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "net_balance": net_balance,
            "income_trend": _get_trend(cur_income, prev_income),
            "expense_trend": _get_trend(cur_expense, prev_expense),
            "balance_trend": _get_trend(cur_balance, prev_balance),
        }

    async def get_category_breakdown(self, record_type: RecordType | None = None) -> list[dict]:
        stmt = select(Record.category, sa_func.sum(Record.amount).label("total")).group_by(Record.category)
        if record_type:
            stmt = stmt.where(Record.type == record_type)
        result = await self.db.execute(stmt)
        return [{"category": row.category, "total": Decimal(str(row.total))} for row in result.all()]

    async def get_trends(self, period: AggregationPeriod, count: int, end_date: date | None = None) -> list[dict]:
        """Return income/expense totals grouped by the given period for the last N periods."""
        today = end_date or date.today()
        periods = []
        
        if period == AggregationPeriod.month:
            for i in range(count - 1, -1, -1):
                dt = today - relativedelta(months=i)
                periods.append(f"{dt.year:04d}-{dt.month:02d}")
            cutoff = today.replace(day=1) - relativedelta(months=count - 1)
        elif period == AggregationPeriod.quarter:
            for i in range(count - 1, -1, -1):
                dt = today - relativedelta(months=3 * i)
                q = (dt.month - 1) // 3 + 1
                periods.append(f"Q{q} {dt.year}")
            # Anchor cutoff to first day of the oldest quarter in the list
            oldest_dt = today - relativedelta(months=3 * (count - 1))
            oldest_q_start_month = 3 * ((oldest_dt.month - 1) // 3) + 1
            cutoff = oldest_dt.replace(month=oldest_q_start_month, day=1)
        elif period == AggregationPeriod.year:
            for i in range(count - 1, -1, -1):
                dt = today - relativedelta(years=i)
                periods.append(f"{dt.year:04d}")
            cutoff = today.replace(month=1, day=1) - relativedelta(years=count - 1)

        stmt = (
            select(Record.date, Record.type, Record.amount)
            .where(Record.date >= cutoff)
        )
        result = await self.db.execute(stmt)

        pivot: dict[str, dict] = {
            p: {"period": p, "income": Decimal("0"), "expense": Decimal("0")}
            for p in periods
        }

        for row in result.all():
            rd = row.date
            rt = row.type
            ra = row.amount
            if period == AggregationPeriod.month:
                p_str = f"{rd.year:04d}-{rd.month:02d}"
            elif period == AggregationPeriod.quarter:
                q = (rd.month - 1) // 3 + 1
                p_str = f"Q{q} {rd.year}"
            elif period == AggregationPeriod.year:
                p_str = f"{rd.year:04d}"
            
            if p_str in pivot:
                pivot[p_str][rt.value] += Decimal(str(ra))

        return list(pivot.values())

    async def get_recent(self, limit: int = 10) -> list[Record]:
        result = await self.db.execute(select(Record).order_by(Record.created_at.desc()).limit(limit))
        return list(result.scalars().all())
