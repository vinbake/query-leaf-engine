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

    def add_answer(self, answer: Answer) -> Optional[str]:
        """
        Process one answer and return the next question node ID or pinhole.

        Returns:
            Next node ID to ask, pinhole indicator, crisis route, or None if complete.
        """
        self.answer_history.append(answer)

        tree = answer.tree
        current_node = self.trees.get(tree.value, {}).get(answer.node_id)

        if not current_node:
            return None

        # 1. Check for crisis routes (Acacia.Q4 safety check)
        if tree == Tree.ACACIA and answer.node_id == "Q4":
            safety = self._evaluate_safety(answer.user_response)
            if safety in [SafetyLevel.UNSURE, SafetyLevel.AT_RISK]:
                return self._crisis_route()

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
            # If no reconciliation signal, treat as pinhole not found yet
            return None

        return next_node if next_node else None

    def finalize_prompt(self, tree: Tree) -> PromptOutput:
        """
        Assemble final prompt from pinhole, AU context, and visitor's signals.
        """
        pinhole = self.pinholes.get(tree)
        if not pinhole:
            raise ValueError(f"No pinhole identified for {tree.value}")

        # Build the prompt
        situation = self._build_situation(tree)
        au_context = self.au_context.get(tree.value, {})
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
            au_context=json.dumps(au_context),
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

    def _crisis_route(self) -> str:
        """Return crisis help indicator and set crisis pinhole"""
        crisis_pinhole = Pinhole(
            tree=Tree.ACACIA,
            root_cause="CRISIS_ROUTE",
            confidence=1.0,
            signals=["Q4"]
        )
        self.pinholes[Tree.ACACIA] = crisis_pinhole
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

        # Pattern 4: Pine + Gum: "Procrastinating" + "Don't feel heard"
        if Tree.PINE in identified and Tree.GUM in identified:
            pine_signal = "procrastin" in identified[Tree.PINE].root_cause.lower()
            gum_signal = "heard" in identified[Tree.GUM].root_cause.lower()
            if pine_signal and gum_signal:
                return (
                    [Tree.PINE, Tree.GUM],
                    "Resentment that they don't support this goal. Fix partnership first."
                )

        return None

    def _build_situation(self, tree: Tree) -> str:
        """
        Reconstruct the visitor's situation from answer history.
        """
        situation_parts = []
        for answer in self.answer_history:
            if answer.tree == tree:
                situation_parts.append(f"{answer.node_id}: {answer.user_response}")
        return " | ".join(situation_parts)

    def _assemble_prompt(self, pinhole: Pinhole, situation: str, au_context: Dict) -> str:
        """
        Assemble rich prompt per spec structure:
        [Situation + Context]
        [Specific ask]
        [AU resource ask]
        [Constraint]
        """
        prompt = f"""
{pinhole.root_cause}

Situation:
{situation}

Specific ask:
Help me understand what's really happening here and what one step I could take this week.

Australian context:
{json.dumps(au_context, indent=2)}

Important: Keep this practical and specific to my situation.
""".strip()
        return prompt

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
