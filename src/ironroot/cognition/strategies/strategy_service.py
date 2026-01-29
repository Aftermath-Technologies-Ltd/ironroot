# Author: Bradley R. Kinnard
"""strategy service layer with gate-blocked promotion."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ironroot.domain.errors import GateFailed, NotFoundError
from ironroot.domain.ids import generate_id, hash_content
from ironroot.storage.models import StrategyRecord
from ironroot.verification.gate_service import get_gate_service


class StrategyService:
    """manages strategy versions, mutation, selection, and promotion."""

    async def register_strategy(
        self,
        session: AsyncSession,
        name: str,
        version: str,
        manifest: dict[str, Any],
    ) -> StrategyRecord:
        """registers a new strategy version."""
        strategy_id = generate_id("str")

        # compute manifest hash for integrity
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        manifest_hash = hash_content(manifest_bytes)

        record = StrategyRecord(
            id=strategy_id,
            name=name,
            version=version,
            manifest_hash=manifest_hash,
            manifest=manifest,
            gate_passed=False,
            promoted=False,
            created_at=datetime.utcnow(),
        )

        session.add(record)
        await session.flush()

        return record

    async def get_strategy(self, session: AsyncSession, strategy_id: str) -> StrategyRecord | None:
        """fetches a strategy by id."""
        result = await session.execute(
            select(StrategyRecord).where(StrategyRecord.id == strategy_id)
        )
        return result.scalar_one_or_none()

    async def list_strategies(
        self,
        session: AsyncSession,
        name: str | None = None,
        promoted_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[StrategyRecord], int]:
        """lists strategies with optional filters."""
        query = select(StrategyRecord)

        if name:
            query = query.where(StrategyRecord.name == name)
        if promoted_only:
            query = query.where(StrategyRecord.promoted.is_(True))

        # count
        count_query = select(StrategyRecord.id)
        if name:
            count_query = count_query.where(StrategyRecord.name == name)
        if promoted_only:
            count_query = count_query.where(StrategyRecord.promoted.is_(True))
        count_result = await session.execute(count_query)
        total = len(count_result.all())

        # paginate
        query = query.order_by(StrategyRecord.created_at.desc())
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)

        return list(result.scalars().all()), total

    async def mark_gate_passed(
        self,
        session: AsyncSession,
        strategy_id: str,
        run_id: str,
    ) -> StrategyRecord:
        """marks that a strategy passed its gate from a run."""
        strategy = await self.get_strategy(session, strategy_id)
        if not strategy:
            raise NotFoundError("strategy", strategy_id)

        # verify the run's gates actually passed
        gate_service = get_gate_service()
        gate_status = await gate_service.get_gate_status(session, run_id)

        if gate_status["status"] != "passed":
            raise GateFailed("full_suite", "cannot mark strategy gate passed without passing run")

        await session.execute(
            update(StrategyRecord).where(StrategyRecord.id == strategy_id).values(gate_passed=True)
        )

        return await self.get_strategy(session, strategy_id)  # type: ignore

    async def promote_strategy(
        self,
        session: AsyncSession,
        strategy_id: str,
    ) -> StrategyRecord:
        """promotes a strategy if gate has passed."""
        strategy = await self.get_strategy(session, strategy_id)
        if not strategy:
            raise NotFoundError("strategy", strategy_id)

        if not strategy.gate_passed:
            raise GateFailed(
                "strategy_promotion",
                f"strategy {strategy_id} has not passed gates, cannot promote",
            )

        await session.execute(
            update(StrategyRecord)
            .where(StrategyRecord.id == strategy_id)
            .values(promoted=True, promoted_at=datetime.utcnow())
        )

        return await self.get_strategy(session, strategy_id)  # type: ignore

    async def mutate_strategy(
        self,
        session: AsyncSession,
        base_strategy_id: str,
        seed: int,
        mutation_rate: float = 0.1,
    ) -> StrategyRecord:
        """creates a mutated variant from a base strategy."""
        import random

        base = await self.get_strategy(session, base_strategy_id)
        if not base:
            raise NotFoundError("strategy", base_strategy_id)

        rng = random.Random(seed)

        # mutate manifest values within bounds
        new_manifest = dict(base.manifest)

        # mutate abstention threshold if present
        if "abstention_threshold" in new_manifest:
            delta = rng.uniform(-mutation_rate, mutation_rate)
            old_value = float(new_manifest["abstention_threshold"])
            new_value = max(0.0, min(1.0, old_value + delta))
            new_manifest["abstention_threshold"] = new_value

        # increment version
        base_version = base.version.split(".")
        if len(base_version) >= 3 and base_version[-1].isdigit():
            patch = int(base_version[-1]) + 1
            new_version = f"{'.'.join(base_version[:-1])}.{patch}"
        else:
            new_version = f"{base.version}.1"

        # record mutation provenance
        new_manifest["mutation_provenance"] = {
            "parent_id": base_strategy_id,
            "seed": seed,
            "mutation_rate": mutation_rate,
        }

        return await self.register_strategy(
            session,
            name=base.name,
            version=new_version,
            manifest=new_manifest,
        )

    async def score_strategy(
        self,
        session: AsyncSession,
        strategy_id: str,
        correctness: float,
        reproducibility: float,
        efficiency: float,
        safety: float,
    ) -> StrategyRecord:
        """updates strategy scores from evaluation."""
        strategy = await self.get_strategy(session, strategy_id)
        if not strategy:
            raise NotFoundError("strategy", strategy_id)

        await session.execute(
            update(StrategyRecord)
            .where(StrategyRecord.id == strategy_id)
            .values(
                correctness_score=correctness,
                reproducibility_score=reproducibility,
                efficiency_score=efficiency,
                safety_score=safety,
            )
        )

        return await self.get_strategy(session, strategy_id)  # type: ignore

    async def select_best(
        self,
        session: AsyncSession,
        name: str,
    ) -> StrategyRecord | None:
        """selects the best strategy by multi-objective scoring."""
        result = await session.execute(
            select(StrategyRecord)
            .where(StrategyRecord.name == name)
            .where(StrategyRecord.gate_passed.is_(True))
            .order_by(
                StrategyRecord.correctness_score.desc().nulls_last(),
                StrategyRecord.reproducibility_score.desc().nulls_last(),
                StrategyRecord.efficiency_score.desc().nulls_last(),
                StrategyRecord.safety_score.desc().nulls_last(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


# singleton
_strategy_service: StrategyService | None = None


def get_strategy_service() -> StrategyService:
    """returns shared strategy service instance."""
    global _strategy_service
    if _strategy_service is None:
        _strategy_service = StrategyService()
    return _strategy_service
