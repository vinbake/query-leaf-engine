"""
AU Context Layer — Tree-specific Australian facts, services, and guidance

This is the swappable data layer for prompts. All AU figures, service names,
phone numbers, and regulatory references live here.

Updated: 2026-09-30 (FY 2025-26)
"""


def load_au_context() -> dict:
    """
    Return Australian context per tree.
    Used by prompt maximiser to inject country-specific guidance.
    """
    return {
        "oak": {
            "name": "Oak (Finance)",
            "services": [
                {
                    "name": "ASIC MoneySmart",
                    "url": "www.moneysmart.gov.au",
                    "description": "Free budget tools and financial guidance"
                },
                {
                    "name": "ASIC MoneyHelper",
                    "url": "www.moneyhelper.org.au",
                    "description": "Retirement and superannuation planning"
                },
                {
                    "name": "Centrelink",
                    "phone": "13 23 17",
                    "description": "Income support payments (if eligible)"
                },
                {
                    "name": "Fair Work Ombudsman",
                    "url": "www.fairwork.gov.au",
                    "description": "Employment entitlements and disputes"
                },
                {
                    "name": "Community Legal Centres",
                    "description": "Free financial and legal advice (varies by state)"
                }
            ],
            "financial_year_info": {
                "tax_free_threshold": "$18,200",
                "year": "2025-26",
                "super_contribution_cap": "$27,500"
            },
            "state_hardship": {
                "nsw": "NSW Community Services hardship assistance",
                "vic": "Victoria emergency relief grants",
                "qld": "Queensland Community Assistance Program",
                "wa": "WA Financial Counselling Service"
            },
            "prompt_guidance": "Include relevant Centrelink thresholds, tax offsets, or state-specific assistance if the situation involves government support. Avoid deficit framing; focus on options."
        },

        "gum": {
            "name": "Gum (Relationship)",
            "services": [
                {
                    "name": "Relationships Australia",
                    "phone": "1300 364 277",
                    "url": "www.relationships.org.au",
                    "description": "Couples counselling, family support, telehealth available"
                },
                {
                    "name": "1800Respect",
                    "phone": "1800 737 732",
                    "description": "Domestic violence support (free, 24/7)"
                },
                {
                    "name": "RUOK",
                    "url": "www.ruok.org.au",
                    "description": "Mental health conversation resources"
                },
                {
                    "name": "Australian Parenting",
                    "url": "www.parentline.com.au",
                    "description": "Parenting support, varies by state"
                }
            ],
            "cultural_note": "Australian relationships often value directness over conflict avoidance. Frame conversations as 'team huddle', not accusation.",
            "prompt_guidance": "Offer Relationships Australia as the primary pathway. If domestic violence is mentioned, always reference 1800Respect. Emphasize team language over blame."
        },

        "acacia": {
            "name": "Acacia (Wellbeing)",
            "crisis_services": [
                {
                    "name": "Lifeline",
                    "phone": "13 11 14",
                    "description": "24/7 crisis line for suicidal thoughts or acute distress",
                    "critical": True
                },
                {
                    "name": "Beyond Blue",
                    "phone": "1300 22 4636",
                    "url": "www.beyondblue.org.au",
                    "description": "Depression and anxiety support, includes chat and video"
                },
                {
                    "name": "Headspace",
                    "url": "www.headspace.com.au",
                    "description": "Mental health for under-25s, free or low-cost"
                }
            ],
            "regular_services": [
                {
                    "name": "Medicare Rebate",
                    "description": "See GP for referral to psychology rebate (10 sessions/year)",
                    "note": "Rebate covers part of cost; out-of-pocket varies"
                },
                {
                    "name": "RUOK",
                    "url": "www.ruok.org.au",
                    "description": "Peer conversation framework"
                },
                {
                    "name": "lifeline.org.au/chat",
                    "description": "Online chat option for people who prefer not to call"
                }
            ],
            "sleep_specific": {
                "gp_first": "See your GP before sleep apps; they can check for sleep apnea, medication effects",
                "resources": "ESSA-accredited exercise physiologists often help with sleep issues"
            },
            "prompt_guidance": "If ANY mention of self-harm, suicide, or feeling unsafe: include Lifeline 13 11 14 and Beyond Blue 1300 22 4636 prominently. Never position these as backup; they are THE path. For ongoing stress, always suggest GP for mental health plan."
        },

        "pine": {
            "name": "Pine (Productivity)",
            "employment": [
                {
                    "name": "Fair Work Ombudsman",
                    "phone": "13 13 94",
                    "url": "www.fairwork.gov.au",
                    "description": "Work hours, rest breaks, reasonable adjustment claims"
                },
                {
                    "name": "WorkCover/NDIS",
                    "description": "If productivity issues are disability-related, explore NDIS support"
                }
            ],
            "cultural_note": "Australian workplace culture is evolving on boundaries. 'No' is increasingly accepted. References to 'work-life balance' and flexible work are culturally appropriate.",
            "prompt_guidance": "If employment-related, reference Fair Work. If boundary issues, normalize saying no. Avoid US-centric productivity frameworks (like 'hustle culture'); emphasize Australian-style pragmatism."
        },

        "wattle": {
            "name": "Wattle (Health)",
            "pathways": [
                {
                    "name": "GP First",
                    "description": "Australian healthcare model: GP is the gateway. Medicare rebates available.",
                    "reminder": "Always suggest seeing your GP first"
                },
                {
                    "name": "Psychology Rebate",
                    "description": "GP can refer for up to 10 psychology sessions/year with Medicare rebate",
                    "note": "Out-of-pocket costs vary by provider"
                },
                {
                    "name": "ESSA (Exercise & Sports Science)",
                    "description": "Exercise physiology is often funded for fatigue, chronic pain, mental health",
                    "url": "www.essa.org.au"
                },
                {
                    "name": "Naturopath/TCM",
                    "note": "Not Medicare-rebated. Some private health insurance covers. TGA regulates, but efficacy claims are limited."
                }
            ],
            "tga_guardrail": "CRITICAL: Never claim a modality 'treats' or 'cures' a condition. Say 'people explore' or 'some people use'. This is a legal TGA boundary in AU.",
            "prompt_guidance": "Frame options as 'people explore conventional medicine, traditional approaches, nutritional changes, movement practice' — never rank them or claim efficacy. Always start with GP. If weight/nutrition mentioned, never diagnose; suggest 'exploring with a GP or dietitian'."
        }
    }


def get_context_by_tree(tree_name: str) -> dict:
    """Retrieve context for a single tree"""
    all_context = load_au_context()
    return all_context.get(tree_name, {})


def validate_context():
    """Quick validation: ensure all required trees are present"""
    context = load_au_context()
    required_trees = ["oak", "gum", "acacia", "pine", "wattle"]
    missing = [t for t in required_trees if t not in context]

    if missing:
        raise ValueError(f"Missing AU context for trees: {missing}")

    return True


if __name__ == "__main__":
    validate_context()
    print("✓ AU context validated")

    # Print sample output
    import json
    context = load_au_context()
    print(f"\nTrees configured: {list(context.keys())}")
    print(f"\nOak services: {len(context['oak']['services'])} configured")
    print(f"Acacia crisis services: {len(context['acacia']['crisis_services'])} configured")
