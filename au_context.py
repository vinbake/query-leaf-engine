"""
AU Context Layer — Tree-specific Australian facts, services, and guidance

This is the swappable data layer for prompts. All AU figures, service names,
phone numbers, and regulatory references live here.

Updated: 2026-10-14 (Oak services corrected; Oak tax and super figures removed until verified at the ATO)
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
                    "name": "National Debt Helpline",
                    "url": "www.ndh.org.au",
                    "description": "Free, confidential financial counselling on 1800 007 007"
                },
                {
                    "name": "Services Australia (Centrelink)",
                    "url": "www.servicesaustralia.gov.au",
                    "description": "Income support payments (if eligible)"
                },
                {
                    "name": "Fair Work Ombudsman",
                    "url": "www.fairwork.gov.au",
                    "description": "If the problem is pay or entitlements at work"
                },
                {
                    "name": "Community Legal Centres",
                    "description": "Free legal advice; what is offered varies by centre"
                }
            ],
            # Per-pinhole service lines (2026-10-17). Each pinhole in trees_config.json
            # names the ones that fit it. Numbers and descriptions read from the
            # services' own pages or MoneySmart on 2026-10-17; recheck before changing.
            "catalogue": {
                "ndh": "National Debt Helpline (1800 007 007, weekdays 9:30am to 4:30pm, ndh.org.au): "
                       "free, confidential financial counselling. Aboriginal and Torres Strait Islander "
                       "people can also call Mob Strong Debt Help (1800 808 488)",
                "way_forward": "Way Forward (1300 045 502): free debt management support, "
                               "including repayment plans",
                "afca": "Australian Financial Complaints Authority (afca.org.au): free, if a lender "
                        "won't help with financial difficulty",
                "moneysmart": "ASIC MoneySmart (moneysmart.gov.au): free budget planner and money guides",
                "services_australia": "Services Australia (servicesaustralia.gov.au): payments "
                                      "I might be eligible for",
                "fair_work": "Fair Work Ombudsman (13 13 94): if my hours or pay changed at work",
                "ato": "Australian Taxation Office (ato.gov.au): if I'm paid as a contractor, "
                       "what tax I need to set aside",
                "nils": "No Interest Loans (nils.com.au): no-interest loans for essentials, "
                        "paid straight to the supplier",
                "ask_izzy": "Ask Izzy (askizzy.org.au): finds nearby emergency funds, food and other help",
                "beyond_blue": "Beyond Blue (1300 22 4636): if the worry is getting heavy",
                "ato_plan": "Australian Taxation Office (ato.gov.au): payment plans for a tax debt "
                            "if I'm in financial difficulty",
                "services_australia_debt": "Services Australia (servicesaustralia.gov.au): ask about "
                                           "repaying a Centrelink debt in amounts I can afford",
            },
            # financial_year_info (tax-free threshold, super cap) removed from Oak's prompt
            # 2026-10-14: the year was a year behind (now FY 2026-27), the super cap was
            # out of date, and neither helps a budget question. Put figures back only
            # when read from the ATO for the current year, and only where they matter.
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
                    "url": "www.headspace.org.au",
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
            # Per-pinhole service lines for the D38 spec path (2026-11-14). Each Acacia pinhole
            # in trees_config.json names the keys that fit it. Texts verified against each
            # service's source on 2026-11-05 (see d38-specs-acacia-draft.md for the provenance
            # table); recheck MindSpot hours before launch (its page is dated 2025).
            "catalogue": {
                "lifeline": "Lifeline (13 11 14, 24 hours, lifeline.org.au): if I'm ever thinking about harming myself or I feel unsafe, I call this first, before anything else in this prompt. Text 0477 13 11 14 and online chat are also available 24 hours.",
                "beyond_blue": "Beyond Blue Support Service (1300 22 4636, beyondblue.org.au): free phone and online (web chat) counselling for stress, anxiety and low mood. The call itself is charged at local-call rates and can cost more from a mobile.",
                "gp_mhtp": "My GP (or a psychiatrist) can prepare a Mental Health Treatment Plan and referral so I can get Medicare-rebated sessions with a psychologist: up to 10 individual sessions a calendar year, in courses of up to 6 with a review in between. The rebate doesn't cover the whole fee, so the gap varies by provider.",
                "medicare_mhc": "Medicare Mental Health Centre (1800 595 212, medicarementalhealth.gov.au/centres): free, no referral and no appointment needed, for anyone who needs mental health support. Check whether there is one near me.",
                "mindspot": "MindSpot (1800 614 434, mindspot.org.au): a free mental health service run by Macquarie University (MQ Health). Phone Mon–Fri 8am–8pm, Sat 8am–6pm, Sydney time, closed NSW public holidays. Not a crisis service.",
                "headspace": "headspace (headspace.org.au): support for young people aged 12 to 25.",
                "gp": "My GP: the starting point for checking physical causes. If my clinic is closed, healthdirect's Service Finder (healthdirect.gov.au) can help me find another GP.",
                "healthdirect": "Healthdirect helpline (1800 022 222, healthdirect.gov.au): registered nurses, 24 hours a day, 7 days a week, to help decide whether to see a GP, manage at home or go to an emergency department. Mobile call charges may apply. (Called Nurse-on-Call in Victoria.)",
                "personal_leave": "Paid personal/carer's leave under the National Employment Standards: 10 days a year for full-time employees, pro rata for part-time. Casual employees don't get paid personal/carer's leave. My employer can ask for evidence that would satisfy a reasonable person, and my award or agreement may say what kind.",
                "flex_request": "I can make a formal request to change my working arrangements if I've had at least 12 months with my employer and I'm a parent or carer of a child of school age or younger, a carer, a person with disability, 55 or older, pregnant, or experiencing family and domestic violence. My employer must answer in writing within 21 days and can only refuse on reasonable business grounds.",
                "eap": "If my employer offers an Employee Assistance Program, it is usually confidential and free to me. Worth asking HR or checking the intranet.",
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
