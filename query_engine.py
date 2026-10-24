"""
The Query Leaf — Wise Man Query Engine
Track 1: Core Narrowing, Reconciliation, and Prompt Assembly Logic
Implementation: Python 3.9+

This module implements:
1. Decision tree narrowing (5-tree engine)
2. Cross-tree reconciliation detection
3. Prompt maximiser assembly
4. Share code generation
"""

import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import secrets


class Tree(Enum):
    """Tree identifiers"""
    OAK = "oak"       # Finance
    GUM = "gum"       # Relationship
    ACACIA = "acacia" # Wellbeing
    PINE = "pine"     # Productivity
    WATTLE = "wattle" # Health


class SafetyLevel(Enum):
    """Safety classification for crisis detection"""
    SAFE = "safe"
    UNSURE = "unsure"
    AT_RISK = "at_risk"


@dataclass
class Answer:
    """Visitor's answer to a question node"""
    node_id: str
    tree: Tree
    user_response: str
    follow_up: Optional[str] = None


@dataclass
class Pinhole:
    """Identified root cause"""
    tree: Tree
    root_cause: str
    confidence: float  # 0.0-1.0
    signals: List[str]  # which answers triggered this
    needs_reconciliation: bool = False
    secondary_trees: List[Tree] = None


@dataclass
class PromptOutput:
    """Final assembled prompt ready for handoff"""
    pinhole: Pinhole
    prompt_text: str
    au_context: str
    share_code: str
    feedback_options: List[str] = None


class QueryEngine:
    """
    Main engine: routes questions → narrows pinhole → detects reconciliation
    → assembles prompt → generates share code
    """

    def __init__(self, trees_config: Dict, au_context_config: Dict):
        """
        Args:
            trees_config: Dict with keys 'oak', 'gum', etc., containing question nodes
            au_context_config: Dict with AU context per tree
        """
        self.trees = trees_config
        self.au_context = au_context_config
        self.answer_history: List[Answer] = []
        self.pinholes: Dict[Tree, Optional[Pinhole]] = {tree: None for tree in Tree}
        self.crisis_kind: Optional[str] = None

    def add_answer(self, answer: Answer) -> Optional[str]:
        """
        Process one answer and return the next question node ID or pinhole.

        Returns:
            Next node ID to ask, pinhole indicator, crisis route, or None if complete.
        """
        self.answer_history.append(answer)

        tree = answer.tree

        # The Wise Man's defining question at a hand-over (added 2026-10-12):
        # "BRIDGE/gum|acacia" asks which tree to carry on in. Returns "<tree>/Q1".
        if answer.node_id.startswith("BRIDGE/"):
            options = [t for t in answer.node_id.split("/", 1)[1].split("|") if t in self.trees]
            # A tree can set its own defining question (Oak, 2026-10-14): the choices
            # include "stay" (carry on in the starting tree), so a visitor who says it
            # is mostly the money is never pushed into another tree. An answer that
            # matches nothing asks again; it is never guessed.
            custom = self.trees.get(tree.value, {}).get("bridge")
            if custom:
                for c in custom.get("choices", []):
                    if c.get("answer") == answer.user_response:
                        if c.get("go") == "stay":
                            return c.get("route")
                        if c.get("go") in options:
                            return f"{c['go']}/Q1"
                return None
            for t in options:
                if self.trees[t].get("bridge_answer") == answer.user_response:
                    return f"{t}/Q1"
            return f"{options[0]}/Q1" if options else None

        current_node = self.trees.get(tree.value, {}).get(answer.node_id)

        if not current_node:
            return None

        # 1. Check for crisis routes. Any node marked safety_check can send the visitor
        # to a crisis screen (2026-10-24: Gum's affair path, not only Acacia Q4). The
        # node's own routes decide; Acacia Q4 keeps its phrase check as well. The
        # node's crisis_kind picks which helplines the screen shows.
        if current_node.get("safety_check"):
            routed = current_node.get("routes", {}).get(answer.user_response) == "CRISIS_ROUTE"
            flagged = (tree == Tree.ACACIA and answer.node_id == "Q4" and
                       self._evaluate_safety(answer.user_response) in [SafetyLevel.UNSURE, SafetyLevel.AT_RISK])
            if routed or flagged:
                return self._crisis_route(tree, answer.node_id, current_node.get("crisis_kind", "self_harm"))

        # 2. Check if answer points to a pinhole
        pinhole = self._detect_pinhole(tree, answer.node_id, answer.user_response)
        if pinhole:
            self.pinholes[tree] = pinhole
            # Check for reconciliation signals
            if self._has_cross_tree_signals():
                return "RECONCILE"
            return "PINHOLE"

        # 3. Get next node from routes
        next_node = current_node.get("routes", {}).get(answer.user_response)

        # 4. Handle special reconciliation route markers
        if next_node and next_node.startswith("RECONCILE"):
            # Trigger reconciliation detection
            reconciliation = self.detect_reconciliation()
            if reconciliation:
                return "RECONCILE"
            return self._hand_over(tree, answer.node_id, next_node)

        # 5. A route that says "stop here" but whose node carries no pinhole text
        # used to crash finalize (Gum Q1 "I don't feel heard", fixed 2026-10-12).
        if next_node == "PINHOLE" and not self.pinholes.get(tree):
            self.pinholes[tree] = Pinhole(
                tree=tree,
                root_cause=current_node.get("default_pinhole") or f"The heart of it: {answer.user_response.lower()}.",
                confidence=0.7,
                signals=[answer.node_id],
            )
            if self._has_cross_tree_signals():
                return "RECONCILE"
            return "PINHOLE"

        return next_node if next_node else None

    def _hand_over(self, tree: Tree, node_id: str, route: str) -> Optional[str]:
        """
        A route such as RECONCILE_OAK or RECONCILE_GUM_OR_ACACIA means the real
        pressure point sits in another tree. Added 2026-10-12: before this the
        engine returned nothing and the visitor was left waiting.

        The starting tree's part is kept as a hand-over pinhole, so the final
        prompt can join both trees. Trees already visited are not offered again,
        so a visitor can never be sent round in a circle.

        Returns "<tree>/Q1" (carry on in that tree), "BRIDGE/<a>|<b>" (ask the
        defining question first), or RECONCILE / PINHOLE when nowhere is left.
        """
        if not self.pinholes.get(tree):
            self.pinholes[tree] = Pinhole(
                tree=tree,
                root_cause=self.trees.get(tree.value, {}).get("handoff_note", "This is part of it, but not all of it."),
                confidence=0.6,
                signals=[node_id],
            )
        visited = {a.tree.value for a in self.answer_history}
        targets = [t.lower() for t in route[len("RECONCILE_"):].split("_OR_")]
        targets = [t for t in targets if t in self.trees and t not in visited]
        if not targets:
            return "RECONCILE" if self._has_cross_tree_signals() else "PINHOLE"
        if len(targets) == 1:
            return f"{targets[0]}/Q1"
        return "BRIDGE/" + "|".join(targets)

    def finalize_prompt(self, tree: Tree) -> PromptOutput:
        """
        Assemble final prompt from pinhole, AU context, and visitor's signals.
        """
        pinhole = self.pinholes.get(tree)
        if not pinhole:
            raise ValueError(f"No pinhole identified for {tree.value}")

        # Build the prompt
        situation = self._build_situation(tree, as_list=True)
        au_context = self.au_context.get(tree.value, {})
        spec = self._prompt_spec(tree, pinhole)
        if spec:
            # The Wise Man's handoff (2026-10-17): the pinhole travels as the
            # visitor's own working view, the visitor's AI is asked to check it
            # first, and the ask and services are chosen for that pinhole.
            prompt_text = self._assemble_from_spec(tree, spec, situation, au_context)
        else:
            prompt_text = self._assemble_prompt(
                pinhole=pinhole,
                situation=situation,
                au_context=au_context
            )

        # Generate share code
        share_code = self._generate_share_code()

        # Standard feedback options
        feedback_options = [
            "brilliant_answer",
            "something_missing",
            "didnt_work"
        ]

        return PromptOutput(
            pinhole=pinhole,
            prompt_text=prompt_text,
            au_context=self._format_au_context(au_context),
            share_code=share_code,
            feedback_options=feedback_options
        )

    def detect_reconciliation(self) -> Optional[Tuple[List[Tree], str]]:
        """
        Scan answer history for cross-tree signals.

        Returns:
            (trees_involved, root_cause) or None
        """
        signals = self._analyze_cross_tree_signals()
        if signals:
            return signals
        return None

    # ========== Private methods ==========

    def _evaluate_safety(self, response: str) -> SafetyLevel:
        """
        Evaluate Acacia.Q4 response for crisis indicators.
        Maps to: safe / unsure / at_risk
        """
        unsafe_phrases = [
            "harm", "hurt", "kill", "suicide", "ending this",
            "not worth", "rather not exist", "don't want to be here"
        ]

        response_lower = response.lower()
        has_unsafe = any(phrase in response_lower for phrase in unsafe_phrases)

        if "plan" in response_lower or has_unsafe:
            return SafetyLevel.AT_RISK
        elif "thoughts" in response_lower or "not sure" in response_lower:
            return SafetyLevel.UNSURE
        return SafetyLevel.SAFE

    def _crisis_route(self, tree: Tree = Tree.ACACIA, node_id: str = "Q4", kind: str = "self_harm") -> str:
        """Return crisis help indicator and set crisis pinhole. The kind (self_harm or
        family_violence) tells the app which helplines to show; nothing else is kept."""
        crisis_pinhole = Pinhole(
            tree=tree,
            root_cause="CRISIS_ROUTE",
            confidence=1.0,
            signals=[node_id]
        )
        self.pinholes[tree] = crisis_pinhole
        self.crisis_kind = kind
        return "CRISIS_ROUTE"

    def _detect_pinhole(self, tree: Tree, node_id: str, response: str) -> Optional[Pinhole]:
        """
        Check if this answer + history points to a pinhole (stop narrowing).
        """
        tree_config = self.trees.get(tree.value, {})
        node = tree_config.get(node_id, {})

        # Check if this node ends narrowing (has "pinholes" field)
        pinholes = node.get("pinholes", {})
        if pinholes and response in pinholes:
            pinhole_text = pinholes[response]
            return Pinhole(
                tree=tree,
                root_cause=pinhole_text,
                confidence=0.85,
                signals=[node_id]
            )

        # Check if node config says "stops_narrowing"
        if node.get("stops_narrowing"):
            pinhole_text = node.get("default_pinhole", "Core issue identified")
            return Pinhole(
                tree=tree,
                root_cause=pinhole_text,
                confidence=0.75,
                signals=[node_id]
            )

        return None

    def _has_cross_tree_signals(self) -> bool:
        """Check if multiple trees have pinholes"""
        identified_trees = [t for t, p in self.pinholes.items() if p is not None]
        return len(identified_trees) > 1

    def _analyze_cross_tree_signals(self) -> Optional[Tuple[List[Tree], str]]:
        """
        Reconciliation detection table per spec.
        Returns (trees_involved, root_cause_narrative)
        """
        identified = {t: p for t, p in self.pinholes.items() if p is not None}
        if any(p.root_cause == "CRISIS_ROUTE" for p in identified.values()):
            return None  # a crisis route on any tree is never reconciled (2026-10-24)

        # Pattern 1: Gum + Acacia: "Fighting about money" + "Sleeping badly"
        # Fixed 2026-10-05 (ISSUE-001): match on the tree pair, like patterns 2 and 3.
        # The old keyword test ("fighting" / "sleep" in the pinhole text) never matched
        # the real pinhole wording. A crisis route is never reconciled into a narrative.
        if Tree.GUM in identified and Tree.ACACIA in identified:
            if identified[Tree.ACACIA].root_cause != "CRISIS_ROUTE":
                return (
                    [Tree.GUM, Tree.ACACIA],
                    "Financial stress → relationship tension → poor sleep. Address stress, not symptoms."
                )

        # Pattern 2: Pine + Gum: "Can't focus" + "Relationship distant"
        if Tree.PINE in identified and Tree.GUM in identified:
            return (
                [Tree.PINE, Tree.GUM],
                "Attention has shifted; real issue is partnership on this goal."
            )

        # Pattern 3: Wattle + Oak: "Tired all the time" + "Money's tight"
        if Tree.WATTLE in identified and Tree.OAK in identified:
            return (
                [Tree.WATTLE, Tree.OAK],
                "Financial stress manifests as fatigue. Fix anxiety, tiredness improves."
            )

        # Patterns 5 to 7 and the fallback added 2026-10-12 with the hand-over.
        if Tree.OAK in identified and Tree.GUM in identified:
            return (
                [Tree.OAK, Tree.GUM],
                "Money stress is driving the tension between you. The real step is facing the numbers together."
            )
        if Tree.OAK in identified and Tree.ACACIA in identified:
            return (
                [Tree.OAK, Tree.ACACIA],
                "Money worry is wearing you down. Easing the worry matters as much as fixing the numbers."
            )
        if Tree.PINE in identified and Tree.ACACIA in identified:
            return (
                [Tree.PINE, Tree.ACACIA],
                "Putting it off says more about how you're feeling than about discipline. Start with the feeling."
            )

        # Pattern 4: Pine + Gum: "Procrastinating" + "Don't feel heard"
        if Tree.PINE in identified and Tree.GUM in identified:
            pine_signal = "procrastin" in identified[Tree.PINE].root_cause.lower()
            gum_signal = "heard" in identified[Tree.GUM].root_cause.lower()
            if pine_signal and gum_signal:
                return (
                    [Tree.PINE, Tree.GUM],
                    "Resentment that they don't support this goal. Fix partnership first."
                )

        if len(identified) > 1:
            return (
                list(identified.keys()),
                "More than one part of life is tangled up in this. Look at them together, not one at a time."
            )

        return None

    def _build_situation(self, tree: Tree, as_list: bool = False) -> str:
        """
        Reconstruct the visitor's situation from answer history, written as the
        question that was asked and the answer given (2026-10-14: it used to print
        node codes such as "Q3: Partly", which meant nothing to the visitor's AI).
        """
        situation_parts = []
        for answer in self.answer_history:
            node = self.trees.get(answer.tree.value, {}).get(answer.node_id, {})
            if node.get("safety_check"):
                continue  # the safety answer is never written into a prompt (2026-10-13)
            if answer.tree == tree and not answer.node_id.startswith("BRIDGE/"):
                question = node.get("question") or answer.node_id
                situation_parts.append(f"{question} — {answer.user_response}")
        if as_list:
            return "\n".join(f"- {part}" for part in situation_parts)
        return " | ".join(situation_parts)

    def finalize_joined(self) -> PromptOutput:
        """
        One prompt for a visitor whose answers ran across more than one tree
        (added 2026-10-12). Leads with the reconciled root cause, then what was
        said in each tree, then each tree's Australian context.
        """
        identified = {t: p for t, p in self.pinholes.items() if p is not None}
        rec = self.detect_reconciliation()
        trees, cause = rec if rec else (list(identified.keys()), "")
        order = [a.tree for a in self.answer_history if a.tree in identified]
        trees = list(dict.fromkeys(order + [t for t in trees if t in identified]))
        lead = cause or " ".join(identified[t].root_cause for t in trees)
        said = []
        for t in trees:
            label = self.trees.get(t.value, {}).get("name", t.value).split(" — ")[0]
            said.append(f"{label}: {self._first_person(t, identified[t])} ({self._build_situation(t)})")
        contexts = [self._format_au_context(self.au_context.get(t.value, {})) for t in trees]
        prompt = f"""
{lead}

What I've said:
""".strip() + "\n" + "\n".join(said) + f"""

Specific ask:
Help me understand how these connect, what is really driving it, and what one step I could take this week.

Australian context:
""" + "\n".join(contexts) + """

Important: Keep this practical and specific to my situation."""
        pinhole = Pinhole(tree=trees[0], root_cause=lead, confidence=0.8,
                          signals=[t.value for t in trees])
        return PromptOutput(
            pinhole=pinhole,
            prompt_text=prompt,
            au_context="\n".join(contexts),
            share_code=self._generate_share_code(),
            feedback_options=["brilliant_answer", "something_missing", "didnt_work"],
        )

    def _format_au_context(self, au_context: Dict) -> str:
        """
        Render the AU context data layer (D29's swappable services/figures,
        au_context.py) as plain sentences for the visitor-facing prompt.

        The data layer also carries internal-only fields — 'prompt_guidance'
        and 'tga_guardrail' — that steer how THIS function writes the
        sentence. They are never echoed verbatim to the visitor; doing so
        (the previous json.dumps(au_context) behaviour) leaked raw Python
        dict syntax into the prompt and, for Wattle, made the TGA self-test
        pass by accident on the guardrail's own instruction text rather
        than on real guardrail-compliant wording in context. Fixed 2026-10-09.
        """
        if not au_context:
            return "No specific Australian services identified for this topic."

        def fmt(s: Dict) -> str:
            contact = s.get("phone") or s.get("url")
            desc = s.get("description") or s.get("note")
            tail = " — ".join(x for x in [contact, desc] if x)
            return f"{s.get('name', '')} ({tail})" if tail else s.get("name", "")

        lines = []

        if "tga_guardrail" in au_context:
            # Wattle (Health): never state a modality "treats" or "cures" a condition —
            # legal TGA boundary. Clinical/Medicare pathways and non-rebated
            # modalities are named separately with their real standing.
            pathways = au_context.get("pathways", [])
            clinical = [p for p in pathways if p.get("name") != "Naturopath/TCM"]
            alt = [p for p in pathways if p.get("name") == "Naturopath/TCM"]
            if clinical:
                lines.append("For practical options, people explore things such as "
                              + "; ".join(fmt(p) for p in clinical) + ".")
            if alt:
                lines.append("Some people also use " + "; ".join(fmt(p) for p in alt)
                              + " — not Medicare-rebated, and efficacy claims are limited under TGA regulation.")
        else:
            for key in ("services", "crisis_services", "regular_services", "employment"):
                items = au_context.get(key)
                if items:
                    lines.append("; ".join(fmt(s) for s in items) + ".")

        fy = au_context.get("financial_year_info")
        if fy:
            lines.append(
                f"For {fy.get('year', 'this financial year')}, the tax-free threshold is "
                f"{fy.get('tax_free_threshold', 'not set')} and the super contribution cap is "
                f"{fy.get('super_contribution_cap', 'not set')}."
            )

        sleep = au_context.get("sleep_specific")
        if sleep:
            lines.extend(v for v in sleep.values() if isinstance(v, str))

        note = au_context.get("cultural_note")
        if note:
            lines.append(note)

        return " ".join(lines) if lines else "No specific Australian services identified for this topic."

    def _prompt_spec(self, tree: Tree, pinhole: Pinhole) -> Optional[Dict]:
        """
        The handoff wording for this pinhole, if the tree supplies one: the node
        that produced the pinhole carries a "prompt" map keyed by the answer
        given there ({formulation, ask, services}). None means the tree has not
        been written this way yet, and the older template is used.
        """
        cfg = self.trees.get(tree.value, {})
        node_id = (pinhole.signals or [None])[-1]
        node = cfg.get(node_id, {}) if node_id else {}
        prompts = node.get("prompt") or {}
        answer = next((a.user_response for a in reversed(self.answer_history)
                       if a.tree == tree and a.node_id == node_id), None)
        return prompts.get(answer) if answer is not None else None

    def _first_person(self, tree: Tree, pinhole: Pinhole) -> str:
        """The pinhole in the visitor's own voice, where the tree supplies it."""
        cfg = self.trees.get(tree.value, {})
        spec = self._prompt_spec(tree, pinhole)
        if spec:
            return spec["formulation"]
        if pinhole.root_cause == cfg.get("handoff_note") and cfg.get("handoff_formulation"):
            return cfg["handoff_formulation"]
        return pinhole.root_cause

    def _assemble_from_spec(self, tree: Tree, spec: Dict, situation: str, au_context: Dict) -> str:
        cfg = self.trees.get(tree.value, {})
        q1 = next((a.user_response for a in self.answer_history
                   if a.tree == tree and a.node_id == "Q1"), None)
        opening = (cfg.get("Q1", {}).get("openings", {}) or {}).get(q1) \
            or cfg.get("default_opening", "I'm trying to work out what's really going on")
        not_this = cfg.get("not_generic", "general tips")
        ask = list(spec.get("ask", []))[:2] + ["pick one step I can take this week"]
        letters = "abc"
        ask_lines = "\n".join(f"({letters[i]}) {a}" for i, a in enumerate(ask))
        catalogue = au_context.get("catalogue", {})
        services = [catalogue[s] for s in spec.get("services", []) if s in catalogue]
        options = "\n".join(f"- {s}" for s in services)
        parts = [
            f"I'm in Australia and {opening}. Here's what I think is really going on: {spec['formulation']}",
            f"What I told the Query Leaf:\n{situation}",
            # D38 (2026-10-17): the Wise Man has already asked the questions. The AI must not
            # ask more — it answers straight away and states assumptions rather than asking.
            f"Please answer straight away — do not ask me any clarifying questions. "
            f"Work on that root cause first, not {not_this}. "
            "If my reading doesn't fit what I've said, or you need something I haven't told you, "
            "say so in one line and tell me what you've assumed, then answer.",
            f"Please help me:\n{ask_lines}",
            "If you're unsure of a figure or rule, say so rather than guessing. Keep it plain and practical.",
        ]
        if options:
            parts.append(f"Australian options to check where they fit:\n{options}")
        return "\n\n".join(parts)

    def _assemble_prompt(self, pinhole: Pinhole, situation: str, au_context: Dict) -> str:
        """
        Generic fallback prompt — used when a tree node has no D38 spec written yet.
        Mirrors the voice and anti-question structure of _assemble_from_spec so visitors
        get a consistent experience regardless of which tree they ran.
        Updated 2026-10-23: added first-person voice, explicit no-questions directive,
        and structured (a)/(b) asks to match D38 standard.
        """
        au_block = self._format_au_context(au_context)
        au_line = f"\n\nAustralian context:\n{au_block}" if au_block else ""
        prompt = f"""I'm in Australia and here's what I think is really going on: {pinhole.root_cause}

What I described to the Query Leaf:
{situation}

Please answer straight away — do not ask me any clarifying questions. If my reading doesn't fit what I've said, or you need something I haven't told you, say so in one line and tell me what you've assumed, then answer.

Please help me:
(a) understand what's actually driving this, in plain terms
(b) pick one step I can take this week{au_line}

If you're unsure of a figure or rule, say so rather than guessing. Keep it plain and practical."""
        return prompt.strip()

    def _generate_share_code(self) -> str:
        """
        Generate 6-char URL-safe code.
        """
        # Use first 6 chars of hex-encoded random 4 bytes
        random_bytes = secrets.token_bytes(4)
        hex_code = hashlib.sha256(random_bytes).hexdigest()[:6].upper()
        return hex_code

    def get_tree_entry_questions(self) -> Dict[str, str]:
        """
        Return all entry questions (first node per tree).
        Used by entry screen to route visitor.
        """
        entry_questions = {}
        for tree_name in self.trees:
            tree_config = self.trees[tree_name]
            q1 = tree_config.get("Q1", {})
            entry_questions[tree_name] = q1.get("question", "")
        return entry_questions

    def serialize_for_cache(self) -> Dict:
        """Serialize session state for caching"""
        return {
            "answer_history": [asdict(a) for a in self.answer_history],
            "pinholes": {
                tree.value: (asdict(p) if p else None)
                for tree, p in self.pinholes.items()
            }
        }


# ========== CONFIG LOADING ==========

def load_trees_config() -> Dict:
    """
    Load decision tree definitions from JSON/YAML.
    Placeholder: returns minimal tree structure.
    """
    return {
        "oak": {
            "Q1": {
                "question": "What's the money problem?",
                "answers": ["Income too low", "Spending too high", "Debt", "Don't know", "One-off shock"],
                "routes": {
                    "Income too low": "Q2.Income",
                    "Spending too high": "Q2.Spending",
                    "Debt": "Q2.Debt"
                }
            },
            "Q2.Income": {
                "question": "Is the income actually too low, or does it feel that way?",
                "answers": ["Below living costs", "Looks OK on paper but doesn't feel real", "Irregular work", "Recently dropped"],
                "pinholes": {
                    "Looks OK on paper but doesn't feel real": "Income irregularity is the real problem, not total amount — you need a buffer plan"
                }
            },
            "Q4": {
                "question": "What's one thing that would feel like relief right now?",
                "stops_narrowing": True,
                "default_pinhole": "You know what would help—let's build that specific relief into your week"
            }
        },
        "acacia": {
            "Q1": {
                "question": "What's going on?",
                "answers": ["Can't sleep", "Exhausted but wired", "Everything feels too much", "Can't focus", "Anxious"]
            },
            "Q4": {
                "question": "Are you safe? Is anyone else at risk?",
                "crisis_detection": True,
                "answers": ["Yes, safe", "Thoughts but no plan", "Not sure"]
            }
        }
        # Oak, Gum, Pine, Wattle fully defined in separate config files
    }


def load_au_context() -> Dict:
    """Load Australian context layer"""
    return {
        "oak": {
            "services": [
                "ASIC MoneySmart",
                "Centrelink payments",
                "Community Legal Centres (free advice)",
                "State hardship assistance"
            ],
            "tax_note": "Current FY threshold: $18,200"
        },
        "gum": {
            "helpline": "Relationships Australia 1300 364 277",
            "note": "Counselling + telehealth available"
        },
        "acacia": {
            "crisis_lines": {
                "lifeline": "13 11 14",
                "beyond_blue": "1300 22 4636"
            },
            "gp_pathway": "Medicare rebate available"
        },
        "pine": {
            "fair_work": "Fair Work Ombudsman (employment issues)"
        },
        "wattle": {
            "note": "See GP first; no TGA efficacy claims"
        }
    }


if __name__ == "__main__":
    # Quick test
    trees = load_trees_config()
    context = load_au_context()
    engine = QueryEngine(trees, context)

    print("Query Engine initialized.")
    print(f"Trees available: {list(trees.keys())}")
    print(f"Entry questions: {engine.get_tree_entry_questions()}")
