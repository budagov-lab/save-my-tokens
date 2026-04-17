"""Detect breaking changes between function contracts."""

from typing import List

from loguru import logger

from src.contracts.contract_models import (
    BreakingChange,
    BreakingChangeType,
    ChangeSeverity,
    ContractComparison,
    FunctionContract,
)


class BreakingChangeDetector:
    """Detect breaking changes between two function contracts."""

    def detect_breaking_changes(
        self, old_contract: FunctionContract, new_contract: FunctionContract
    ) -> ContractComparison:
        """Compare contracts and detect breaking changes.

        Args:
            old_contract: Previous version of function contract
            new_contract: New version of function contract

        Returns:
            ContractComparison with detected changes
        """
        breaking_changes: List[BreakingChange] = []
        non_breaking_changes: List[str] = []

        # 1. Check for removed parameters
        old_params = {p.name for p in old_contract.signature.parameters}
        new_params = {p.name for p in new_contract.signature.parameters}
        removed_params = old_params - new_params

        if removed_params:
            breaking_changes.append(
                BreakingChange(
                    type=BreakingChangeType.PARAMETER_REMOVED,
                    severity=ChangeSeverity.HIGH,
                    impact=f"Parameters removed: {', '.join(removed_params)}. "
                    "All callers passing these parameters will fail.",
                    affected_elements=removed_params,
                )
            )

        # 2. Check for parameters that became required
        old_required = {p.name for p in old_contract.signature.parameters if not p.is_optional}
        new_required = {p.name for p in new_contract.signature.parameters if not p.is_optional}
        became_required = new_required - old_required

        if became_required:
            breaking_changes.append(
                BreakingChange(
                    type=BreakingChangeType.PARAMETER_REQUIRED_NOW,
                    severity=ChangeSeverity.HIGH,
                    impact=f"Parameters now required: {', '.join(became_required)}. "
                    "Callers not providing these will fail.",
                    affected_elements=became_required,
                )
            )

        # 3. Check for parameter type changes
        old_param_types = {p.name: p.type_hint for p in old_contract.signature.parameters}
        new_param_types = {p.name: p.type_hint for p in new_contract.signature.parameters}

        for param_name in old_params & new_params:
            old_type = old_param_types.get(param_name)
            new_type = new_param_types.get(param_name)

            if old_type and new_type and old_type != new_type:
                if self._is_type_narrowed(old_type, new_type):
                    breaking_changes.append(
                        BreakingChange(
                            type=BreakingChangeType.PARAMETER_TYPE_CHANGED,
                            severity=ChangeSeverity.HIGH,
                            impact=f"Parameter '{param_name}' type narrowed: {old_type} → {new_type}. "
                            "Callers with old type may fail.",
                            affected_elements={param_name},
                            old_value=old_type,
                            new_value=new_type,
                        )
                    )

        # 4. Check return type changes
        old_return = old_contract.signature.return_type
        new_return = new_contract.signature.return_type

        if old_return and new_return and old_return != new_return:
            if self._is_type_narrowed(old_return, new_return):
                breaking_changes.append(
                    BreakingChange(
                        type=BreakingChangeType.RETURN_TYPE_NARROWED,
                        severity=ChangeSeverity.MEDIUM,
                        impact=f"Return type narrowed: {old_return} → {new_return}. "
                        "Callers expecting old type may fail.",
                        affected_elements={"return"},
                        old_value=old_return,
                        new_value=new_return,
                    )
                )

        # 5. Check for removed exceptions
        old_exceptions = set(old_contract.signature.raises)
        new_exceptions = set(new_contract.signature.raises)
        removed_exceptions = old_exceptions - new_exceptions

        # Note: removed exceptions are NOT breaking (good news for callers)
        if removed_exceptions:
            non_breaking_changes.append(
                f"Removed exceptions: {', '.join(removed_exceptions)}"
            )

        # 6. Check for added exceptions (informational)
        added_exceptions = new_exceptions - old_exceptions
        if added_exceptions:
            breaking_changes.append(
                BreakingChange(
                    type=BreakingChangeType.EXCEPTION_ADDED,
                    severity=ChangeSeverity.LOW,
                    impact=f"New exceptions may be raised: {', '.join(added_exceptions)}. "
                    "Callers may need updated error handling.",
                    affected_elements=added_exceptions,
                )
            )

        # 7. Check for added optional parameters (non-breaking)
        added_params = new_params - old_params
        if added_params:
            new_param_map = {p.name: p for p in new_contract.signature.parameters}
            all_optional = all(
                new_param_map[p].is_optional for p in added_params
            )

            if all_optional:
                non_breaking_changes.append(
                    f"Added optional parameters: {', '.join(added_params)}"
                )

        # 8. Check preconditions (stricter preconditions are breaking)
        if old_contract.preconditions and new_contract.preconditions:
            # Simple heuristic: if new preconditions > old, it's potentially breaking
            if len(new_contract.preconditions) > len(old_contract.preconditions):
                breaking_changes.append(
                    BreakingChange(
                        type=BreakingChangeType.PRECONDITION_ADDED,
                        severity=ChangeSeverity.MEDIUM,
                        impact="New preconditions added. "
                        "Existing callers may violate new requirements.",
                        affected_elements={"preconditions"},
                    )
                )

        # Calculate compatibility score
        is_compatible = len(breaking_changes) == 0
        compatibility_score = 1.0 - (len(breaking_changes) * 0.3)  # Each breaking change reduces score
        compatibility_score = max(0.0, min(1.0, compatibility_score))

        logger.info(
            f"Contract comparison for {old_contract.symbol.name}: "
            f"breaking={len(breaking_changes)}, non_breaking={len(non_breaking_changes)}, "
            f"compatible={is_compatible}"
        )

        return ContractComparison(
            old_contract=old_contract,
            new_contract=new_contract,
            breaking_changes=breaking_changes,
            non_breaking_changes=non_breaking_changes,
            is_compatible=is_compatible,
            compatibility_score=compatibility_score,
        )

    def _is_type_narrowed(self, old_type: str, new_type: str) -> bool:
        """Check if a type has been narrowed (more specific).

        Args:
            old_type: Old type string
            new_type: New type string

        Returns:
            True if new_type is narrower than old_type
        """
        # Simple heuristics
        # Note: this is not a complete type system, just common patterns

        # Any/object → specific type is narrowing
        if old_type in ["Any", "object"]:
            return True

        # Union narrowing: Union[A, B] → A
        if "Union" in old_type and "Union" not in new_type:
            return True

        # Optional removal: Optional[T] → T
        if "Optional" in old_type and "Optional" not in new_type:
            return True

        # Supertype → subtype (heuristic: if lengths differ significantly)
        if len(new_type) < len(old_type):
            return False  # Probably broadened

        return False  # Default: types are compatible
