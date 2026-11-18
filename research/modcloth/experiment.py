"""ModCloth fit classifier: naive vs class balanced, evaluated on unseen products."""
import json, re, sys
import pandas as pd, numpy as np
from sklearn.model_selection import GroupShuffleSplit
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import recall_score, balanced_accuracy_score, accuracy_score, confusion_matrix, f1_score

rows = [json.loads(l) for l in open(sys.argv[1])]
df = pd.DataFrame(rows)
def h(s):
    if not isinstance(s, str): return np.nan
    m = re.match(r'(\d+)ft\s*(\d+)?', s)
    return int(m.group(1)) * 12 + int(m.group(2) or 0) if m else np.nan
df['height_inches'] = df['height'].map(h)
df = df[df['fit'].isin(['small', 'fit', 'large'])]
y = df['fit']; groups = df['item_id']
print('records', len(df), dict(y.value_counts(normalize=True).round(3)))
tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(df, y, groups))
LABELS = ['small', 'fit', 'large']

def run(name, feats, clf):
    num = [f for f in feats if f != 'category']; cat = [f for f in feats if f == 'category']
    pre = ColumnTransformer([('n', Pipeline([('i', SimpleImputer(strategy='median')), ('s', StandardScaler())]), num)] +
                            ([('c', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat)] if cat else []))
    m = Pipeline([('p', pre), ('m', clf)]).fit(df.iloc[tr][feats], y.iloc[tr])
    p = m.predict(df.iloc[te][feats]); t = y.iloc[te]
    r = recall_score(t, p, labels=LABELS, average=None)
    out = dict(model=name, features='+'.join(feats), small=r[0], fit=r[1], large=r[2],
               macro_recall=balanced_accuracy_score(t, p), macro_f1=f1_score(t, p, labels=LABELS, average='macro'), accuracy=accuracy_score(t, p))
    print(f"{name:42s} small {r[0]:.3f} fit {r[1]:.3f} large {r[2]:.3f} | macro recall {out['macro_recall']:.3f} macro F1 {out['macro_f1']:.3f} acc {out['accuracy']:.3f}")
    return out, confusion_matrix(t, p, labels=LABELS)

# Wardrobe features: the shopper's OWN past fit outcomes and usual size, from TRAINING rows only (no leakage).
train = df.iloc[tr]
u = train.groupby('user_id').agg(u_small=('fit', lambda s: (s == 'small').mean()), u_large=('fit', lambda s: (s == 'large').mean()),
                                 u_size=('size', 'median'), u_n=('fit', 'size'))
df = df.join(u, on='user_id')
df['size_vs_usual'] = df['size'] - df['u_size']
# For training rows, a user's own label leaks into u_small/u_large; recompute leave one out for those rows.
for col, lab in (('u_small', 'small'), ('u_large', 'large')):
    tr_idx = df.index[tr]
    n = df.loc[tr_idx, 'u_n']; hit = (df.loc[tr_idx, 'fit'] == lab).astype(float)
    df.loc[tr_idx, col] = np.where(n > 1, (df.loc[tr_idx, col] * n - hit) / (n - 1).clip(lower=1), np.nan)
print('test rows whose shopper has history in training:', round(df.iloc[te]['u_n'].notna().mean(), 3))
F = ['size', 'height_inches', 'category']
FW = ['size', 'category', 'u_small', 'u_large', 'size_vs_usual']
F2 = ['size', 'category']
res = []
res.append(run('Majority class baseline', F2, DummyClassifier(strategy='most_frequent'))[0])
res.append(run('Random forest, naive', F, RandomForestClassifier(n_estimators=200, min_samples_leaf=5, random_state=0, n_jobs=-1))[0])
res.append(run('Random forest, class balanced', F, RandomForestClassifier(n_estimators=200, min_samples_leaf=5, class_weight='balanced', random_state=0, n_jobs=-1))[0])
res.append(run('Logistic regression, naive', F, LogisticRegression(max_iter=1000))[0])
res.append(run('Logistic regression, class balanced', F, LogisticRegression(max_iter=1000, class_weight='balanced'))[0])
o, cm_naive = run('Gradient boosting, naive', F, HistGradientBoostingClassifier(random_state=0))
res.append(o)
o, cm_bal = run('Gradient boosting, class balanced', F, HistGradientBoostingClassifier(class_weight='balanced', random_state=0))
res.append(o)
print('-- no body data (size + category only) --')
res.append(run('Gradient boosting, balanced, no height', F2, HistGradientBoostingClassifier(class_weight='balanced', random_state=0))[0])
print('-- wardrobe features: own past fit + usual size, no body data --')
res.append(run('Gradient boosting, balanced, wardrobe', FW, HistGradientBoostingClassifier(class_weight='balanced', random_state=0))[0])
res.append(run('Logistic regression, balanced, wardrobe', FW, LogisticRegression(max_iter=2000, class_weight='balanced'))[0])
pd.DataFrame(res).round(3).to_csv('modcloth_results.csv', index=False)
print('confusion naive (rows true small/fit/large):\n', cm_naive, '\nconfusion balanced:\n', cm_bal)
