import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, numpy as np
from matplotlib import font_manager
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':15})
models=['Always says "fit"\n(baseline)','Naive model','Class balanced\nmodel']
small=[0,0.0,54.2]; fit=[100,100,24.2]; large=[0,0.2,45.3]; macro=[33.3,33.4,41.2]
x=np.arange(3); w=0.25
fig,ax=plt.subplots(figsize=(13,6.2),dpi=200); fig.patch.set_facecolor('#faf8f3'); ax.set_facecolor('#faf8f3')
c=['#b5583c','#9aa59d','#2f3e56']
for i,(vals,lab) in enumerate([(small,'Too small'),(fit,'Fit'),(large,'Too large')]):
    b=ax.bar(x+(i-1)*w,vals,w*0.92,color=c[i],label=f'Recall: {lab}')
    for r,v in zip(b,vals): ax.text(r.get_x()+r.get_width()/2,v+1.5,f'{v:.0f}%',ha='center',fontsize=13,color='#222')
for xi,m in zip(x,macro): ax.text(xi,112,f'Macro recall {m:.1f}%',ha='center',fontsize=14,fontweight='bold',color='#222')
ax.set_xticks(x,models,fontsize=15); ax.set_ylim(0,122); ax.set_yticks([0,25,50,75,100],['0%','25%','50%','75%','100%'],color='#555')
for s in ['top','right','left']: ax.spines[s].set_visible(False)
ax.axhline(33.3,ls=':',color='#999',lw=1); ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(0.5,-0.13),ncol=3,fontsize=14)
plt.tight_layout(); plt.savefig('slide10_recall_chart.png',facecolor=fig.get_facecolor())
