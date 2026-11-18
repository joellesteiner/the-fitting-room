"""The Fitting Room engine.

Three layers, kept separate on purpose:
1. NLP retrieval (TF IDF) picks the closest catalogue product to the shopper's description.
2. A transparent chart rule turns the owned size and its fit report into a starting size.
3. A Bayesian belief over sizes says how confident we are, abstains below a threshold,
   and is updated by post delivery fit reports (prior x likelihood, then normalise).

The sensor model is learned from ModCloth fit reports. The prior's width and the abstain
threshold are still design assumptions, to be tuned in a pilot.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import json
import math
import re
from pathlib import Path

CHART = 'https://www.levi.com/GB/en_GB/info/sizechart'
GUIDE = 'https://www.levi.com/GB/en_GB/clothing/women/jeans/straight/c/levi_clothing_women_jeans_straight'
ORIGINAL = 'https://www.levi.com/GB/en_GB/clothing/women/jeans/501-original/c/levi_clothing_women_jeans_501_original'

# 'similarity' says how comparable the product is to the owned reference (501 Original).
# It sets how wide the belief is: less comparable cut, wider belief, lower confidence.
CATALOG = [
    {'id': '501', 'name': "501® Original", 'similarity': 'same',
     'desc': 'original classic straight leg high waist rigid no stretch 100 percent cotton button fly denim jeans',
     'fit': 'Classic straight', 'stretch': 'No stretch (100% cotton on listed style)', 'source': ORIGINAL,
     'evidence': 'Brand listing describes 501 Original as classic straight and labels a 100% cotton/no-stretch listing'},
    {'id': '90s', 'name': "501® ’90s", 'similarity': 'family',
     'desc': '90s relaxed slouchy loose straight leg mid rise denim jeans',
     'fit': 'Loose straight, mid rise', 'stretch': 'Not verified across variants', 'source': GUIDE,
     'evidence': 'Brand category describes 501 90s as mid-rise loose straight'},
    {'id': 'curve', 'name': "501® Curve", 'similarity': 'family',
     'desc': 'curve curvy seat thigh extra room straight leg touch stretch denim jeans',
     'fit': 'Roomier seat and thigh', 'stretch': 'Touch of stretch (brand fit description)', 'source': GUIDE,
     'evidence': 'Brand category says more room in seat/thigh and a touch of stretch'},
    {'id': 'ribcage', 'name': 'Ribcage Straight Ankle', 'similarity': 'different',
     'desc': 'ribcage super high rise waist defining 14 inch rise straight leg ankle jeans',
     'fit': 'Super-high-rise straight ankle', 'stretch': 'Not verified across variants', 'source': GUIDE,
     'evidence': 'Brand category describes high rise, 14-inch rise and straight leg'},
    {'id': '724', 'name': '724™ High Rise Straight', 'similarity': 'different',
     'desc': '724 high rise slim fit straight leg modern denim jeans',
     'fit': 'High rise, slim straight', 'stretch': 'Not verified across variants', 'source': GUIDE,
     'evidence': 'Brand category describes high rise and slim fit'},
]

WAIST = {24: 64, 25: 66, 26: 69, 27: 72, 28: 74, 29: 77, 30: 79, 31: 83, 32: 87, 33: 90, 34: 96}
HIP = {24: 86, 25: 89, 26: 91.5, 27: 94, 28: 96.5, 29: 99, 30: 101, 31: 105, 32: 109, 33: 113, 34: 118}
SIZES = sorted(WAIST)
INTENT = {'fitted': -2, 'regular': 0, 'relaxed': 3, 'oversized': 6}
FEEL_LABEL = {-2: 'a little tight', 0: 'just right', 2: 'a little loose'}

# ---- Bayesian settings (illustrative assumptions, stated on screen) ----
ABSTAIN_BELOW = 0.50          # recommend only if the top size holds at least 50% of the belief
RETRIEVAL_MIN = 0.075         # below this TF IDF score we do not trust the product match
SPREAD = {'same': 0.70, 'family': 0.75, 'different': 1.20}   # belief width, in size steps
OVERSIZED_EXTRA = 0.40        # sizing up for an oversized look is unreliable, widen further
LEAN = 0.15                   # a tight or loose report nudges belief further in that direction
# Sensor model: P(report | true size minus size worn), by difference in size steps.
# Learned from ModCloth repeat buyers by research/backtest/backtest.py (see the notebook there).
MODEL_FILE = Path(__file__).parent / 'model' / 'sensor_learned.json'


def load_sensor(path=MODEL_FILE):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))['sensor']
    table = {int(d): {r: float(p) for r, p in row.items()} for d, row in raw.items()}
    if sorted(table) != [-2, -1, 0, 1, 2]:
        raise ValueError('Sensor model must cover size differences from -2 to 2')
    for row in table.values():
        if set(row) != {'tight', 'right', 'loose'} or abs(sum(row.values()) - 1) > 0.01:
            raise ValueError('Each sensor row must give tight, right and loose probabilities summing to 1')
    return table


SENSOR = load_sensor()

V = TfidfVectorizer(ngram_range=(1, 2), stop_words='english')
X = V.fit_transform([p['desc'] + ' ' + p['name'] for p in CATALOG])


def keyword_score(query, desc):
    q = set(re.findall(r'[a-z0-9]+', query.lower())) - {'jeans', 'denim', 'the', 'a', 'with', 'and', 'for', 'pair', 'of', 'i', 'want'}
    d = set(re.findall(r'[a-z0-9]+', desc.lower()))
    return len(q & d)


def rank(query, method='tfidf'):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Describe the style you want')
    if re.search(r'\b(shirt|dress|skirt|handbag|shoes|trainers|jacket)\b', query.lower()):
        raise ValueError('This prototype supports jeans only. Please search for a jeans style.')
    if method == 'keyword':
        return sorted([(p, keyword_score(query, p['desc'] + ' ' + p['name'])) for p in CATALOG], key=lambda x: (-x[1], x[0]['id']))
    sims = cosine_similarity(V.transform([query]), X)[0]
    return sorted([(p, float(sims[i])) for i, p in enumerate(CATALOG)], key=lambda x: -x[1])


def normalise(weights):
    total = sum(weights.values())
    return {s: w / total for s, w in weights.items()}


def prior_belief(centre_size, spread, lean):
    """Discretised Gaussian over chart sizes, centred on the rule's size, nudged by the fit report."""
    i0 = SIZES.index(centre_size) + lean
    return normalise({s: math.exp(-((i - i0) ** 2) / (2 * spread ** 2)) for i, s in enumerate(SIZES)})


def likelihood(report, true_size, worn_size, sensor=None):
    d = SIZES.index(true_size) - SIZES.index(worn_size)
    return (sensor or SENSOR)[max(-2, min(2, d))][report]


def update_belief(belief, worn_size, report, sensor=None):
    """One Bayes update: posterior is proportional to likelihood times prior."""
    if report not in ('tight', 'right', 'loose'):
        raise ValueError('Report must be tight, right or loose')
    worn_size = int(worn_size)
    if worn_size not in WAIST:
        raise ValueError('Worn size is outside the published chart range')
    prior = {int(s): float(p) for s, p in belief.items()}
    if set(prior) != set(SIZES) or abs(sum(prior.values()) - 1) > 0.01:
        raise ValueError('Belief must cover every chart size and sum to 1')
    prior = normalise(prior)
    unnorm = {s: likelihood(report, s, worn_size, sensor) * prior[s] for s in SIZES}
    evidence = sum(unnorm.values())
    return normalise(unnorm), evidence


def decide(belief):
    best = max(belief, key=belief.get)
    return best, belief[best], belief[best] >= ABSTAIN_BELOW


def window(belief, centre, n=2):
    """The sizes shown as bars: centre plus n either side, clipped to the chart."""
    i = SIZES.index(centre)
    return SIZES[max(0, i - n): i + n + 1]


def pct(belief):
    return {str(s): round(p, 4) for s, p in belief.items()}


def recommend(owned_size, feel, intent, query):
    try:
        owned_size = int(owned_size)
        feel = int(feel)
    except (TypeError, ValueError):
        raise ValueError('Select a valid saved size and fit')
    if owned_size not in WAIST:
        raise ValueError('This size is outside the published chart range')
    if feel not in (-2, 0, 2):
        raise ValueError('Invalid saved fit feedback')
    if intent not in INTENT:
        raise ValueError('Select your preferred fit')

    found = rank(query)
    best, score = found[0]
    reference = WAIST[owned_size]
    # Tight (feel -2) means the body needs more room, so the target goes UP. Never size down after 'tight'.
    target = reference - feel + INTENT[intent]
    size = min(WAIST, key=lambda s: (abs(WAIST[s] - target), abs(s - owned_size)))
    if feel < 0 and size < owned_size:
        size = owned_size

    spread = SPREAD[best['similarity']] + (OVERSIZED_EXTRA if intent == 'oversized' else 0)
    lean = LEAN if feel < 0 else -LEAN if feel > 0 else 0
    belief = prior_belief(size, spread, lean)
    top, confidence, confident = decide(belief)

    reasons = []
    if score < RETRIEVAL_MIN:
        confident = False
        reasons.append('We could not confidently match that description to a product we have fit data for.')
    if best['similarity'] == 'different':
        reasons.append(f"{best['name']} is a different cut and rise from your 501s, so your reference garment is a weak guide.")
    if intent == 'oversized':
        reasons.append('Sizing up is an unreliable way to get an oversized look; a purpose cut loose style is safer.')
    if not confident and not reasons:
        reasons.append(f'The top size holds only {round(confidence * 100)}% of our belief, below our 50% bar.')

    caution = ['Published waist values describe bodies, not finished jeans.',
               'Fit report probabilities are learned from another retailer (ModCloth); confidence is calibrated there, not yet on this catalogue.']
    if best['stretch'] != 'No stretch (100% cotton on listed style)':
        caution.append('Stretch properties for this exact product variant are not fully verified.')

    return {
        'decision': 'recommend' if confident else 'abstain',
        'size': f'W{top}', 'size_num': top, 'confidence': round(confidence, 4),
        'belief': pct(belief), 'window': window(belief, top),
        'abstain_reasons': reasons if not confident else [],
        'product': best['name'], 'product_id': best['id'], 'fit': best['fit'], 'stretch': best['stretch'],
        'similarity': best['similarity'], 'retrieval_score': round(score, 3),
        'alternatives': [{'id': p['id'], 'name': p['name'], 'score': round(v, 3)} for p, v in found[1:3]],
        'reference_waist_cm': reference, 'target_waist_cm': target, 'recommended_chart_waist_cm': WAIST[size],
        'rule_size': f'W{size}', 'spread': spread, 'threshold': ABSTAIN_BELOW,
        'source': best['source'], 'chart_source': CHART, 'evidence': best['evidence'], 'warnings': caution,
        'method': 'TF IDF selects the product; a chart rule sets the starting size; a Bayesian belief sets confidence or abstains',
        'input': {'owned_size': owned_size, 'feel': feel, 'intent': intent, 'query': query},
    }


def report(belief, worn_size, report_value):
    prior = normalise({int(s): float(p) for s, p in belief.items()})
    posterior, evidence = update_belief(prior, worn_size, report_value)
    top, confidence, confident = decide(posterior)
    worn = int(worn_size)
    return {
        'decision': 'recommend' if confident else 'abstain',
        'size': f'W{top}', 'size_num': top, 'confidence': round(confidence, 4),
        'prior': pct(prior), 'belief': pct(posterior), 'window': window(posterior, top),
        'worn': worn, 'report': report_value, 'evidence': round(evidence, 4),
        'likelihoods': {str(s): likelihood(report_value, s, worn) for s in SIZES},
    }
