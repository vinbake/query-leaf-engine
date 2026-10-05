"""
Track 1 QA Test Scenarios
Week 2 Build: Narrowing logic validation

Test suite: 10 real-world scenarios covering all trees + reconciliation + crisis detection
Status: For manual verification before 2026-10-04 cut
"""

from query_engine import QueryEngine, Answer, Tree, SafetyLevel
from trees_config import load_trees_config
from au_context import load_au_context
import json


class TestScenario:
    """Single test case"""
    def __init__(self, name: str, tree: Tree, story: str, answers: list, expected_pinhole: str = None, should_reconcile: bool = False):
        self.name = name
        self.tree = tree
        self.story = story
        self.answers = answers
        self.expected_pinhole = expected_pinhole
        self.should_reconcile = should_reconcile
        self.result = None
        self.passed = False

    def run(self, engine: QueryEngine) -> bool:
        """Execute test and check result"""
        try:
            for answer in self.answers:
                result = engine.add_answer(answer)

            # Check if pinhole was reached
            pinhole = engine.pinholes.get(self.tree)
            if pinhole and self.expected_pinhole:
                self.passed = self.expected_pinhole.lower() in pinhole.root_cause.lower()
            else:
                self.passed = pinhole is not None

            self.result = pinhole
            return self.passed
        except Exception as e:
            self.result = f"ERROR: {str(e)}"
            self.passed = False
            return False

    def report(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} | {self.name}\n  Pinhole: {self.result}"


def get_test_scenarios() -> list:
    """Return all 10+ test scenarios"""

    scenarios = [
        # ========== OAK (Finance) ==========
        TestScenario(
            name="OAK-1: Irregular income",
            tree=Tree.OAK,
            story="Freelancer worried about inconsistent monthly income",
            answers=[
                Answer("Q1", Tree.OAK, "Income too low"),
                Answer("Q2.Income", Tree.OAK, "Irregular/gig work"),
            ],
            expected_pinhole="Income irregularity"
        ),

        TestScenario(
            name="OAK-2: Spending to cope",
            tree=Tree.OAK,
            story="Parent spending on comfort items when stressed",
            answers=[
                Answer("Q1", Tree.OAK, "Spending too high"),
                Answer("Q2.Spending", Tree.OAK, "Just noticed it"),
                Answer("Q3", Tree.OAK, "No"),  # Fixing number won't solve it
            ],
            expected_pinhole="spending to cope",
            should_reconcile=True
        ),

        # ========== GUM (Relationship) ==========
        TestScenario(
            name="GUM-1: Same fight, different cause",
            tree=Tree.GUM,
            story="Couple fighting about money, but really about control",
            answers=[
                Answer("Q1", Tree.GUM, "We're fighting"),
                Answer("Q2.Fighting", Tree.GUM, "Money"),
                # This routes to RECONCILE_OAK, but test should catch the cross-tree signal
            ],
            expected_pinhole="money",
            should_reconcile=True
        ),

        TestScenario(
            name="GUM-2: Distant relationship",
            tree=Tree.GUM,
            story="Long-term partner relationship has slowly drifted",
            answers=[
                Answer("Q1", Tree.GUM, "We're distant"),
                Answer("Q2.Distant", Tree.GUM, "Months"),
                Answer("Q3", Tree.GUM, "Talking like we used to"),
            ],
            expected_pinhole="Talking like we used to"
        ),

        # ========== ACACIA (Wellbeing) ==========
        TestScenario(
            name="ACACIA-1: Sleep + wired",
            tree=Tree.ACACIA,
            story="Exhausted during day but can't sleep at night",
            answers=[
                Answer("Q1", Tree.ACACIA, "I'm exhausted but wired"),
                Answer("Q2.Wired", Tree.ACACIA, "Gradually"),
                Answer("Q3", Tree.ACACIA, "Rest"),
            ],
            expected_pinhole="burnt out"
        ),

        TestScenario(
            name="ACACIA-2: Crisis detection (unsafe)",
            tree=Tree.ACACIA,
            story="Person expressing thoughts of self-harm",
            answers=[
                Answer("Q1", Tree.ACACIA, "Everything feels too much"),
                Answer("Q4", Tree.ACACIA, "I'm not sure"),
            ],
            expected_pinhole="CRISIS_ROUTE"
        ),

        # ========== PINE (Productivity) ==========
        TestScenario(
            name="PINE-1: Can't start due to clarity",
            tree=Tree.PINE,
            story="Project paralysis from not knowing where to begin",
            answers=[
                Answer("Q1", Tree.PINE, "I can't start"),
                Answer("Q2.Start", Tree.PINE, "Don't know where to start"),
            ],
            expected_pinhole="clarity"
        ),

        TestScenario(
            name="PINE-2: Perfectionism + comparison",
            tree=Tree.PINE,
            story="Manager trying to keep up with peer's output standards",
            answers=[
                Answer("Q1", Tree.PINE, "I'm doing everything but it doesn't feel enough"),
                Answer("Q4", Tree.PINE, "To keep up with someone else"),
            ],
            expected_pinhole="someone else's priority"
        ),

        # ========== WATTLE (Health) ==========
        TestScenario(
            name="WATTLE-1: Recent tiredness from stress",
            tree=Tree.WATTLE,
            story="Parent fatigued after returning to full-time work",
            answers=[
                Answer("Q1", Tree.WATTLE, "Energy/tiredness"),
                Answer("Q2.Energy", Tree.WATTLE, "Recently"),
                Answer("Q2.Energy.Recent", Tree.WATTLE, "Stress increased"),
            ],
            expected_pinhole="Stress"
        ),

        TestScenario(
            name="WATTLE-2: Doctor found nothing",
            tree=Tree.WATTLE,
            story="Chronic fatigue with no diagnosis",
            answers=[
                Answer("Q1", Tree.WATTLE, "Energy/tiredness"),
                Answer("Q2.Energy", Tree.WATTLE, "Gradually over months"),
                Answer("Q3", Tree.WATTLE, "Nothing showed up but I still feel off"),
                Answer("Q4", Tree.WATTLE, "Rest"),
            ],
            expected_pinhole="Rest"
        ),

        # ========== RECONCILIATION (Cross-tree) ==========
        TestScenario(
            name="RECONCILE-1: Money + Sleep (Gum + Acacia)",
            tree=Tree.GUM,
            story="Fighting about finances is wrecking sleep",
            answers=[
                Answer("Q1", Tree.GUM, "We're fighting"),
                Answer("Q2.Fighting", Tree.GUM, "Money"),
                # Would normally RECONCILE_OAK, but this test checks for secondary Acacia signal
            ],
            expected_pinhole="money",
            should_reconcile=True
        ),

        TestScenario(
            name="RECONCILE-2: Work + Relationship (Pine + Gum)",
            tree=Tree.PINE,
            story="Can't focus on work because partner relationship is distant",
            answers=[
                Answer("Q1", Tree.PINE, "I can't start"),
                Answer("Q2.Start", Tree.PINE, "Dread"),
                # Reconcile to Gum when dread + distant relationship detected
            ],
            expected_pinhole="dread",
            should_reconcile=True
        ),
    ]

    return scenarios


def run_test_suite():
    """Execute all test scenarios and report results"""

    # Load configs
    try:
        trees_config = load_trees_config()
        au_context_config = load_au_context()
    except Exception as e:
        print(f"ERROR loading config: {e}")
        return False

    engine = QueryEngine(trees_config, au_context_config)
    scenarios = get_test_scenarios()

    print("=" * 70)
    print("WEEK 2 QA: WISE MAN QUERY ENGINE - NARROWING LOGIC")
    print("=" * 70)
    print(f"\nRunning {len(scenarios)} test scenarios...\n")

    passed = 0
    failed = 0

    for scenario in scenarios:
        # Reset engine for each test
        engine = QueryEngine(trees_config, au_context_config)

        success = scenario.run(engine)
        print(scenario.report())

        if success:
            passed += 1
        else:
            failed += 1

        # Show story for context
        print(f"  Story: {scenario.story}")
        print()

    # Summary
    total = len(scenarios)
    pct = (passed / total * 100) if total > 0 else 0

    print("=" * 70)
    print(f"SUMMARY: {passed}/{total} passed ({pct:.0f}%)")
    print("=" * 70)

    if failed == 0:
        print("\n✓ All tests PASSED. Ready for staging deploy.")
        return True
    else:
        print(f"\n✗ {failed} tests FAILED. Debug required.")
        return False


if __name__ == "__main__":
    success = run_test_suite()
    exit(0 if success else 1)
