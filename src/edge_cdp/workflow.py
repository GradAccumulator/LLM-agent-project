from __future__ import annotations

from dataclasses import dataclass, field
import secrets
from time import monotonic
from typing import Any, Callable

from .controller import (
    EdgeCdpController,
    EdgeCdpError,
    StaleElementReferenceError,
)


def _normalized(value: Any) -> str:
    return " ".join(
        str(value or "").split()
    ).casefold()


def _public_hint(
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "element_ref": record.get(
            "element_ref"
        ),
        "tab_ref": record.get(
            "tab_ref"
        ),
        "kind": record.get("kind"),
        "tag": record.get("tag"),
        "type": record.get("type"),
        "role": record.get("role"),
        "label": record.get("label"),
        "href": record.get("href"),
        "placeholder": record.get(
            "placeholder"
        ),
        "disabled": record.get(
            "disabled"
        ),
        "safety": record.get(
            "safety"
        ),
    }


@dataclass(slots=True)
class _ElementHint:
    ref: str
    tab_ref: str
    kind: str
    record: dict[str, Any]
    created_at: float
    expires_at: float


@dataclass(slots=True)
class _Workflow:
    ref: str
    goal: str
    created_at: float
    expires_at: float
    status: str
    baseline: dict[str, Any]
    steps: list[dict[str, Any]] = field(
        default_factory=list
    )
    last_verification: (
        dict[str, Any] | None
    ) = None


class EdgeWorkflowCoordinator:
    """Safe orchestration above EdgeCdpController.

    It adds:
    - title/URL tab search
    - label/href element search
    - strict stale-reference re-resolution
    - new-tab detection and selection
    - per-workflow action evidence
    - final multi-condition verification

    Sensitive action and field blocking remains enforced by the
    underlying EdgeCdpController on every action and retry.
    """

    def __init__(
        self,
        controller: EdgeCdpController,
        *,
        clock: Callable[[], float] = monotonic,
        workflow_ttl_seconds: float = 900.0,
        hint_ttl_seconds: float = 900.0,
        max_workflow_steps: int = 20,
        recovery_limit: int = 100,
        auto_select_new_tab: bool = True,
    ) -> None:
        if workflow_ttl_seconds <= 0:
            raise ValueError(
                "workflow_ttl_seconds must be positive."
            )
        if hint_ttl_seconds <= 0:
            raise ValueError(
                "hint_ttl_seconds must be positive."
            )
        if not 1 <= max_workflow_steps <= 100:
            raise ValueError(
                "max_workflow_steps must be between 1 and 100."
            )
        if not 1 <= recovery_limit <= 500:
            raise ValueError(
                "recovery_limit must be between 1 and 500."
            )

        self.controller = controller
        self._clock = clock
        self.workflow_ttl_seconds = (
            workflow_ttl_seconds
        )
        self.hint_ttl_seconds = (
            hint_ttl_seconds
        )
        self.max_workflow_steps = (
            max_workflow_steps
        )
        controller_config = getattr(
            controller,
            "config",
            None,
        )
        self.recovery_limit = min(
            recovery_limit,
            int(
                getattr(
                    controller_config,
                    "max_elements",
                    recovery_limit,
                )
            ),
        )
        self.auto_select_new_tab = (
            auto_select_new_tab
        )
        self._hints: dict[
            str,
            _ElementHint,
        ] = {}
        self._workflows: dict[
            str,
            _Workflow,
        ] = {}

    @property
    def allow_dom_actions(self) -> bool:
        return bool(
            getattr(
                self.controller,
                "allow_dom_actions",
                False,
            )
        )

    @property
    def allow_tab_close(self) -> bool:
        return bool(
            getattr(
                self.controller,
                "allow_tab_close",
                False,
            )
        )

    def _purge(self) -> None:
        now = self._clock()
        for ref in [
            ref
            for ref, hint
            in self._hints.items()
            if now >= hint.expires_at
        ]:
            self._hints.pop(ref, None)

        for ref in [
            ref
            for ref, workflow
            in self._workflows.items()
            if now >= workflow.expires_at
        ]:
            self._workflows.pop(
                ref,
                None,
            )

    def _remember_elements(
        self,
        result: dict[str, Any],
    ) -> None:
        self._purge()
        now = self._clock()
        for raw in (
            result.get("elements")
            or []
        ):
            if not isinstance(raw, dict):
                continue
            ref = str(
                raw.get(
                    "element_ref"
                )
                or ""
            ).strip()
            tab_ref = str(
                raw.get("tab_ref")
                or result.get(
                    "tab_ref"
                )
                or ""
            ).strip()
            kind = str(
                raw.get("kind")
                or ""
            ).strip()
            if (
                not ref
                or not tab_ref
                or not kind
            ):
                continue
            self._hints[ref] = (
                _ElementHint(
                    ref=ref,
                    tab_ref=tab_ref,
                    kind=kind,
                    record=_public_hint(
                        raw
                    ),
                    created_at=now,
                    expires_at=(
                        now
                        + self
                        .hint_ttl_seconds
                    ),
                )
            )

    def list_tabs(
        self,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        return (
            self.controller
            .list_tabs(
                limit=limit
            )
        )

    @staticmethod
    def _tab_score(
        query: str,
        tab: dict[str, Any],
    ) -> int:
        title = _normalized(
            tab.get("title")
        )
        url = _normalized(
            tab.get("url")
        )
        if query == title:
            return 120
        if query == url:
            return 115
        score = 0
        if title.startswith(query):
            score = max(score, 100)
        elif query in title:
            score = max(score, 80)
        if url.startswith(query):
            score = max(score, 90)
        elif query in url:
            score = max(score, 70)
        return score

    def find_tabs(
        self,
        *,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        normalized = _normalized(
            query
        )
        if not normalized:
            raise EdgeCdpError(
                "query must not be empty."
            )
        if not 1 <= limit <= 200:
            raise EdgeCdpError(
                "limit must be between 1 and 200."
            )

        listing = self.list_tabs(
            limit=200
        )
        matches: list[
            dict[str, Any]
        ] = []
        for tab in (
            listing.get("tabs")
            or []
        ):
            if not isinstance(tab, dict):
                continue
            score = self._tab_score(
                normalized,
                tab,
            )
            if score <= 0:
                continue
            record = dict(tab)
            record["match_score"] = (
                score
            )
            matches.append(record)

        matches.sort(
            key=lambda item: (
                -int(
                    item.get(
                        "match_score",
                        0,
                    )
                ),
                str(
                    item.get(
                        "title"
                    )
                    or ""
                ).casefold(),
            )
        )
        matches = matches[:limit]
        unique_best = bool(
            matches
            and (
                len(matches) == 1
                or matches[0][
                    "match_score"
                ]
                > matches[1][
                    "match_score"
                ]
            )
        )
        return {
            "query": query,
            "count": len(matches),
            "matches": matches,
            "unique_best": (
                unique_best
            ),
            "best_tab_ref": (
                matches[0].get(
                    "tab_ref"
                )
                if unique_best
                else None
            ),
        }

    def select_tab(
        self,
        *,
        tab_ref: str,
        workflow_ref: (
            str | None
        ) = None,
    ) -> dict[str, Any]:
        result = (
            self.controller
            .select_tab(
                tab_ref=tab_ref
            )
        )
        self._record_step(
            workflow_ref,
            action=(
                "select_tab"
            ),
            result=result,
            verified=bool(
                result.get(
                    "selected"
                )
            ),
        )
        return result

    def get_page_info(
        self,
        *,
        tab_ref: str | None,
        include_text: bool,
    ) -> dict[str, Any]:
        return (
            self.controller
            .get_page_info(
                tab_ref=tab_ref,
                include_text=(
                    include_text
                ),
            )
        )

    def list_elements(
        self,
        *,
        tab_ref: str | None,
        kind: str,
        limit: int,
    ) -> dict[str, Any]:
        result = (
            self.controller
            .list_elements(
                tab_ref=tab_ref,
                kind=kind,
                limit=limit,
            )
        )
        self._remember_elements(
            result
        )
        return result

    @staticmethod
    def _query_score(
        query: str,
        record: dict[str, Any],
    ) -> int:
        label = _normalized(
            record.get("label")
        )
        href = _normalized(
            record.get("href")
        )
        placeholder = _normalized(
            record.get(
                "placeholder"
            )
        )
        fields = (
            (label, 120, 100, 80),
            (placeholder, 110, 90, 70),
            (href, 105, 85, 65),
        )
        score = 0
        for value, exact, prefix, contains in fields:
            if not value:
                continue
            if query == value:
                score = max(
                    score,
                    exact,
                )
            elif value.startswith(
                query
            ):
                score = max(
                    score,
                    prefix,
                )
            elif query in value:
                score = max(
                    score,
                    contains,
                )
        return score

    def find_element(
        self,
        *,
        tab_ref: str | None,
        kind: str,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        normalized = _normalized(
            query
        )
        if not normalized:
            raise EdgeCdpError(
                "query must not be empty."
            )
        result = self.list_elements(
            tab_ref=tab_ref,
            kind=kind,
            limit=min(
                self.recovery_limit,
                max(limit, 1),
            ),
        )
        matches: list[
            dict[str, Any]
        ] = []
        for record in (
            result.get("elements")
            or []
        ):
            if not isinstance(
                record,
                dict,
            ):
                continue
            score = self._query_score(
                normalized,
                record,
            )
            if score <= 0:
                continue
            match = dict(record)
            match["match_score"] = (
                score
            )
            matches.append(match)

        matches.sort(
            key=lambda item: (
                -int(
                    item.get(
                        "match_score",
                        0,
                    )
                ),
                str(
                    item.get(
                        "label"
                    )
                    or ""
                ).casefold(),
            )
        )
        matches = matches[:limit]
        unique_best = bool(
            matches
            and (
                len(matches) == 1
                or matches[0][
                    "match_score"
                ]
                >= (
                    matches[1][
                        "match_score"
                    ]
                    + 15
                )
            )
        )
        best = (
            matches[0]
            if unique_best
            else None
        )
        return {
            "tab_ref": result.get(
                "tab_ref"
            ),
            "title": result.get(
                "title"
            ),
            "url": result.get(
                "url"
            ),
            "kind": kind,
            "query": query,
            "count": len(matches),
            "matches": matches,
            "unique_best": (
                unique_best
            ),
            "best_element_ref": (
                best.get(
                    "element_ref"
                )
                if best
                else None
            ),
            "message": (
                "unique_best=true인 경우에만 자동 대상 선택에 "
                "사용하세요. safety.allowed는 실행 직전에 다시 검사됩니다."
            ),
        }

    @staticmethod
    def _recovery_score(
        original: dict[str, Any],
        candidate: dict[str, Any],
    ) -> int:
        if (
            str(
                original.get(
                    "kind"
                )
                or ""
            )
            != str(
                candidate.get(
                    "kind"
                )
                or ""
            )
        ):
            return -1

        safety = (
            candidate.get(
                "safety"
            )
            or {}
        )
        if (
            not isinstance(
                safety,
                dict,
            )
            or safety.get(
                "allowed"
            )
            is not True
        ):
            return -1

        score = 20
        original_href = (
            _normalized(
                original.get(
                    "href"
                )
            )
        )
        candidate_href = (
            _normalized(
                candidate.get(
                    "href"
                )
            )
        )
        original_label = (
            _normalized(
                original.get(
                    "label"
                )
            )
        )
        candidate_label = (
            _normalized(
                candidate.get(
                    "label"
                )
            )
        )
        original_placeholder = (
            _normalized(
                original.get(
                    "placeholder"
                )
            )
        )
        candidate_placeholder = (
            _normalized(
                candidate.get(
                    "placeholder"
                )
            )
        )

        if original_href:
            if (
                candidate_href
                == original_href
            ):
                score += 100
            else:
                score -= 80

        if original_label:
            if (
                candidate_label
                == original_label
            ):
                score += 70
            elif (
                original_label
                in candidate_label
                or candidate_label
                in original_label
            ):
                score += 30

        if original_placeholder:
            if (
                candidate_placeholder
                == original_placeholder
            ):
                score += 60
            elif (
                original_placeholder
                in candidate_placeholder
                or candidate_placeholder
                in original_placeholder
            ):
                score += 25

        for key in (
            "tag",
            "type",
            "role",
        ):
            value = _normalized(
                original.get(key)
            )
            if (
                value
                and value
                == _normalized(
                    candidate.get(
                        key
                    )
                )
            ):
                score += 5
        return score

    def _recover_element(
        self,
        element_ref: str,
    ) -> tuple[
        str,
        dict[str, Any],
        dict[str, Any],
    ]:
        self._purge()
        hint = self._hints.get(
            element_ref
        )
        if hint is None:
            raise StaleElementReferenceError(
                "The element reference expired and no safe recovery "
                "hint is available. List the elements again."
            )

        result = self.list_elements(
            tab_ref=hint.tab_ref,
            kind=hint.kind,
            limit=self.recovery_limit,
        )
        ranked: list[
            tuple[
                int,
                dict[str, Any],
            ]
        ] = []
        for candidate in (
            result.get("elements")
            or []
        ):
            if not isinstance(
                candidate,
                dict,
            ):
                continue
            score = (
                self._recovery_score(
                    hint.record,
                    candidate,
                )
            )
            if score >= 80:
                ranked.append(
                    (
                        score,
                        candidate,
                    )
                )

        ranked.sort(
            key=lambda item: (
                -item[0],
                str(
                    item[1].get(
                        "label"
                    )
                    or ""
                ).casefold(),
            )
        )
        if not ranked:
            raise StaleElementReferenceError(
                "The page changed and no sufficiently similar safe "
                "element could be recovered. Inspect the page again."
            )
        if (
            len(ranked) > 1
            and ranked[0][0]
            < ranked[1][0] + 15
        ):
            raise StaleElementReferenceError(
                "The page changed and element recovery is ambiguous. "
                "List elements again and choose an exact reference."
            )

        score, record = ranked[0]
        new_ref = str(
            record.get(
                "element_ref"
            )
            or ""
        )
        if not new_ref:
            raise StaleElementReferenceError(
                "Recovered element did not return a valid reference."
            )
        return (
            new_ref,
            record,
            {
                "recovered": True,
                "old_element_ref": (
                    element_ref
                ),
                "new_element_ref": (
                    new_ref
                ),
                "match_score": score,
                "reason": (
                    "stale reference was re-resolved to one "
                    "unambiguous safe element"
                ),
            },
        )

    def get_element(
        self,
        *,
        element_ref: str,
    ) -> dict[str, Any]:
        try:
            result = (
                self.controller
                .get_element(
                    element_ref=(
                        element_ref
                    )
                )
            )
            self._remember_elements(
                {
                    "tab_ref": (
                        result.get(
                            "tab_ref"
                        )
                    ),
                    "elements": [
                        result
                    ],
                }
            )
            result["recovery"] = {
                "recovered": False,
            }
            return result
        except (
            StaleElementReferenceError
        ):
            (
                new_ref,
                record,
                recovery,
            ) = self._recover_element(
                element_ref
            )
            result = (
                self.controller
                .get_element(
                    element_ref=new_ref
                )
            )
            result["recovery"] = (
                recovery
            )
            return result

    def _preflight_element(
        self,
        element_ref: str,
    ) -> tuple[
        str,
        dict[str, Any],
    ]:
        try:
            record = (
                self.controller
                .get_element(
                    element_ref=(
                        element_ref
                    )
                )
            )
            self._remember_elements(
                {
                    "tab_ref": (
                        record.get(
                            "tab_ref"
                        )
                    ),
                    "elements": [
                        record
                    ],
                }
            )
            return (
                element_ref,
                {
                    "recovered": False,
                },
            )
        except (
            StaleElementReferenceError
        ):
            (
                new_ref,
                _,
                recovery,
            ) = self._recover_element(
                element_ref
            )
            # Re-run the controller safety/fingerprint check immediately
            # before execution.
            self.controller.get_element(
                element_ref=new_ref
            )
            return (
                new_ref,
                recovery,
            )

    def _tabs_by_ref(
        self,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, Any],
    ]:
        listing = self.list_tabs(
            limit=200
        )
        return (
            {
                str(
                    tab.get(
                        "tab_ref"
                    )
                ): tab
                for tab in (
                    listing.get(
                        "tabs"
                    )
                    or []
                )
                if isinstance(
                    tab,
                    dict,
                )
                and tab.get(
                    "tab_ref"
                )
            },
            listing,
        )

    def click_element(
        self,
        *,
        element_ref: str,
        workflow_ref: (
            str | None
        ) = None,
    ) -> dict[str, Any]:
        before_tabs, _ = (
            self._tabs_by_ref()
        )
        (
            effective_ref,
            recovery,
        ) = self._preflight_element(
            element_ref
        )

        result = (
            self.controller
            .click_element(
                element_ref=(
                    effective_ref
                )
            )
        )

        after_tabs, listing = (
            self._tabs_by_ref()
        )
        new_refs = [
            ref
            for ref
            in after_tabs
            if ref not in before_tabs
        ]
        new_tabs = [
            after_tabs[ref]
            for ref in new_refs
        ]

        selected_new_tab = None
        if (
            self.auto_select_new_tab
            and len(new_refs) == 1
        ):
            try:
                selection = (
                    self.controller
                    .select_tab(
                        tab_ref=(
                            new_refs[0]
                        )
                    )
                )
                selected_new_tab = (
                    selection.get(
                        "tab"
                    )
                )
            except EdgeCdpError:
                selected_new_tab = None

        result["requested_element_ref"] = (
            element_ref
        )
        result["effective_element_ref"] = (
            effective_ref
        )
        result["recovery"] = recovery
        result["new_tabs"] = (
            new_tabs
        )
        result["new_tab_count"] = len(
            new_tabs
        )
        result["selected_new_tab"] = (
            selected_new_tab
        )
        result["active_tab_ref"] = (
            (
                selected_new_tab
                or {}
            ).get(
                "tab_ref"
            )
            or listing.get(
                "selected_tab_ref"
            )
        )
        if new_tabs:
            result["observed_change"] = (
                True
            )
            result["verified"] = True
            result[
                "verification_strength"
            ] = "strong"

        self._record_step(
            workflow_ref,
            action=(
                "click_element"
            ),
            result=result,
            verified=bool(
                result.get(
                    "clicked"
                )
                and result.get(
                    "verified"
                )
            ),
        )
        return result

    def fill_element(
        self,
        *,
        element_ref: str,
        value: str,
        workflow_ref: (
            str | None
        ) = None,
    ) -> dict[str, Any]:
        (
            effective_ref,
            recovery,
        ) = self._preflight_element(
            element_ref
        )
        result = (
            self.controller
            .fill_element(
                element_ref=(
                    effective_ref
                ),
                value=value,
            )
        )
        result["requested_element_ref"] = (
            element_ref
        )
        result["effective_element_ref"] = (
            effective_ref
        )
        result["recovery"] = recovery
        self._record_step(
            workflow_ref,
            action=(
                "fill_element"
            ),
            result=result,
            verified=bool(
                result.get(
                    "value_set"
                )
                and result.get(
                    "verified"
                )
            ),
        )
        return result

    def _snapshot(
        self,
        *,
        include_text: bool,
    ) -> dict[str, Any]:
        listing = self.list_tabs(
            limit=200
        )
        tabs = [
            dict(tab)
            for tab in (
                listing.get(
                    "tabs"
                )
                or []
            )
            if isinstance(
                tab,
                dict,
            )
        ]
        selected_ref = (
            listing.get(
                "selected_tab_ref"
            )
        )
        selected = next(
            (
                tab
                for tab in tabs
                if tab.get(
                    "selected"
                )
            ),
            None,
        )
        if selected is not None:
            selected_ref = (
                selected.get(
                    "tab_ref"
                )
            )
        elif tabs:
            selected = tabs[0]
            selected_ref = (
                selected.get(
                    "tab_ref"
                )
            )

        page_info = None
        if selected_ref:
            try:
                page_info = (
                    self.get_page_info(
                        tab_ref=str(
                            selected_ref
                        ),
                        include_text=(
                            include_text
                        ),
                    )
                )
            except EdgeCdpError as exc:
                page_info = {
                    "tab_ref": (
                        selected_ref
                    ),
                    "error": str(exc),
                }

        return {
            "tab_count": len(tabs),
            "tabs": tabs,
            "selected_tab_ref": (
                selected_ref
            ),
            "selected_page": (
                page_info
            ),
        }

    def begin_workflow(
        self,
        *,
        goal: str,
        tab_ref: (
            str | None
        ) = None,
    ) -> dict[str, Any]:
        normalized_goal = (
            " ".join(
                goal.split()
            )
        )
        if not normalized_goal:
            raise EdgeCdpError(
                "goal must not be empty."
            )
        if len(normalized_goal) > 500:
            raise EdgeCdpError(
                "goal must not exceed 500 characters."
            )

        if tab_ref:
            self.controller.select_tab(
                tab_ref=tab_ref
            )

        self._purge()
        now = self._clock()
        ref = (
            "edge_flow_"
            + secrets.token_hex(6)
        )
        baseline = self._snapshot(
            include_text=False
        )
        workflow = _Workflow(
            ref=ref,
            goal=normalized_goal,
            created_at=now,
            expires_at=(
                now
                + self
                .workflow_ttl_seconds
            ),
            status="active",
            baseline=baseline,
        )
        self._workflows[ref] = (
            workflow
        )
        return {
            "workflow_ref": ref,
            "goal": normalized_goal,
            "status": "active",
            "baseline": baseline,
            "workflow_ttl_seconds": (
                self
                .workflow_ttl_seconds
            ),
            "max_workflow_steps": (
                self
                .max_workflow_steps
            ),
            "message": (
                "Edge 다단계 작업 추적을 시작했습니다. "
                "행동 도구에 workflow_ref를 전달하고 마지막에 "
                "edge_cdp_verify_workflow로 전체 결과를 검증하세요."
            ),
        }

    def _resolve_workflow(
        self,
        workflow_ref: str,
    ) -> _Workflow:
        self._purge()
        ref = workflow_ref.strip()
        workflow = (
            self._workflows.get(
                ref
            )
        )
        if workflow is None:
            raise EdgeCdpError(
                "Edge workflow reference is missing or expired."
            )
        workflow.expires_at = (
            self._clock()
            + self
            .workflow_ttl_seconds
        )
        return workflow

    def _record_step(
        self,
        workflow_ref: (
            str | None
        ),
        *,
        action: str,
        result: dict[str, Any],
        verified: bool,
    ) -> None:
        if not workflow_ref:
            return
        workflow = (
            self._resolve_workflow(
                workflow_ref
            )
        )
        if workflow.status not in {
            "active",
            "verification_failed",
        }:
            raise EdgeCdpError(
                "This Edge workflow is already completed."
            )
        if (
            len(workflow.steps)
            >= self.max_workflow_steps
        ):
            raise EdgeCdpError(
                "The Edge workflow reached its maximum step count."
            )
        workflow.steps.append(
            {
                "index": (
                    len(
                        workflow.steps
                    )
                    + 1
                ),
                "action": action,
                "verified": (
                    verified
                ),
                "recovery": (
                    result.get(
                        "recovery"
                    )
                ),
                "new_tab_count": (
                    result.get(
                        "new_tab_count"
                    )
                ),
                "active_tab_ref": (
                    result.get(
                        "active_tab_ref"
                    )
                ),
                "evidence": {
                    key: result.get(
                        key
                    )
                    for key in (
                        "element",
                        "tab",
                        "before",
                        "after",
                        "characters",
                        "observed_change",
                        "verification_strength",
                    )
                    if key in result
                },
            }
        )
        workflow.status = (
            "active"
        )

    @staticmethod
    def _workflow_public(
        workflow: _Workflow,
    ) -> dict[str, Any]:
        return {
            "workflow_ref": (
                workflow.ref
            ),
            "goal": workflow.goal,
            "status": (
                workflow.status
            ),
            "baseline": (
                workflow.baseline
            ),
            "step_count": len(
                workflow.steps
            ),
            "steps": [
                dict(step)
                for step
                in workflow.steps
            ],
            "last_verification": (
                workflow
                .last_verification
            ),
        }

    def get_workflow(
        self,
        *,
        workflow_ref: str,
    ) -> dict[str, Any]:
        return self._workflow_public(
            self._resolve_workflow(
                workflow_ref
            )
        )

    def verify_workflow(
        self,
        *,
        workflow_ref: str,
        expected_url_contains: str = "",
        expected_title_contains: str = "",
        expected_text_contains: str = "",
        minimum_tab_count: (
            int | None
        ) = None,
        require_all_steps_verified: bool = True,
    ) -> dict[str, Any]:
        if (
            minimum_tab_count is not None
            and not 0 <= minimum_tab_count <= 200
        ):
            raise EdgeCdpError(
                "minimum_tab_count must be between 0 and 200."
            )

        workflow = (
            self._resolve_workflow(
                workflow_ref
            )
        )
        current = self._snapshot(
            include_text=bool(
                expected_text_contains
            )
        )
        page = (
            current.get(
                "selected_page"
            )
            or {}
        )
        checks: list[
            dict[str, Any]
        ] = []

        if require_all_steps_verified:
            failed_steps = [
                int(
                    step.get(
                        "index",
                        0,
                    )
                )
                for step
                in workflow.steps
                if step.get(
                    "verified"
                )
                is not True
            ]
            checks.append(
                {
                    "name": (
                        "all_steps_verified"
                    ),
                    "passed": (
                        not failed_steps
                        and bool(
                            workflow.steps
                        )
                    ),
                    "failed_steps": (
                        failed_steps
                    ),
                    "step_count": len(
                        workflow.steps
                    ),
                }
            )

        expected_url = (
            _normalized(
                expected_url_contains
            )
        )
        if expected_url:
            actual_url = (
                _normalized(
                    page.get("url")
                )
            )
            checks.append(
                {
                    "name": (
                        "url_contains"
                    ),
                    "passed": (
                        expected_url
                        in actual_url
                    ),
                    "expected": (
                        expected_url_contains
                    ),
                    "actual": (
                        page.get("url")
                    ),
                }
            )

        expected_title = (
            _normalized(
                expected_title_contains
            )
        )
        if expected_title:
            actual_title = (
                _normalized(
                    page.get(
                        "title"
                    )
                )
            )
            checks.append(
                {
                    "name": (
                        "title_contains"
                    ),
                    "passed": (
                        expected_title
                        in actual_title
                    ),
                    "expected": (
                        expected_title_contains
                    ),
                    "actual": (
                        page.get(
                            "title"
                        )
                    ),
                }
            )

        expected_text = (
            _normalized(
                expected_text_contains
            )
        )
        if expected_text:
            actual_text = (
                _normalized(
                    page.get("text")
                )
            )
            checks.append(
                {
                    "name": (
                        "text_contains"
                    ),
                    "passed": (
                        expected_text
                        in actual_text
                    ),
                    "expected": (
                        expected_text_contains
                    ),
                    "actual_text_characters": (
                        page.get(
                            "text_characters"
                        )
                    ),
                }
            )

        if minimum_tab_count is not None:
            actual_count = int(
                current.get(
                    "tab_count",
                    0,
                )
            )
            checks.append(
                {
                    "name": (
                        "minimum_tab_count"
                    ),
                    "passed": (
                        actual_count
                        >= minimum_tab_count
                    ),
                    "expected": (
                        minimum_tab_count
                    ),
                    "actual": (
                        actual_count
                    ),
                }
            )

        if not checks:
            checks.append(
                {
                    "name": (
                        "workflow_has_verified_steps"
                    ),
                    "passed": bool(
                        workflow.steps
                    )
                    and all(
                        step.get(
                            "verified"
                        )
                        is True
                        for step
                        in workflow.steps
                    ),
                    "step_count": len(
                        workflow.steps
                    ),
                }
            )

        verified = all(
            check.get(
                "passed"
            )
            is True
            for check in checks
        )
        result = {
            "workflow_ref": (
                workflow.ref
            ),
            "goal": workflow.goal,
            "verified": verified,
            "checks": checks,
            "baseline": (
                workflow.baseline
            ),
            "current": current,
            "step_count": len(
                workflow.steps
            ),
            "status": (
                "completed"
                if verified
                else (
                    "verification_failed"
                )
            ),
            "message": (
                "다단계 Edge 작업의 행동 기록과 최종 페이지 조건을 "
                "모두 확인했습니다."
                if verified
                else (
                    "전체 검증 조건을 충족하지 못했습니다. 실패한 "
                    "조건을 확인하고 현재 단계만 수정해 재시도하세요."
                )
            ),
        }
        workflow.status = (
            result["status"]
        )
        workflow.last_verification = (
            result
        )
        return result
