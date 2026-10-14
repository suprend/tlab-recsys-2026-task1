"""Notebook-oriented static charts; inputs are reviewed aggregate JSON only.

Contracts: daily=line (31 UTC dates); missing=bar (9 columns);
history=bar (user/event bins and purchase-prior bins, separate denominators);
categories=bar (top12); coverage=100% stacked bar (3 fixed cutoffs);
delay=bar (4 disjoint nearest-prior-view intervals); transitions=heatmap.
Palette: blue root + neutral; coverage uses blue/gold/orange/olive and hatch.
Footprint: 11x5 or 12x5 inch, 150dpi PNG, checked in notebook and exported images.
"""
import datetime as dt
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np

BLUE = '#356A9A'
GOLD = '#C7A34D'
ORANGE = '#C27C4E'
OLIVE = '#818650'
INK = '#293039'


def create(quality, users, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.spines.top': False,
        'axes.spines.right': False, 'axes.labelcolor': INK, 'text.color': INK,
        'axes.titleweight': 'bold', 'axes.grid': False, 'figure.facecolor': 'white'})
    paths = []

    def finish(fig, name, title, subtitle):
        fig.suptitle(title, x=.06, ha='left', fontsize=16, y=.99)
        fig.text(.06,.915,subtitle,ha='left',fontsize=10,color='#555D64')
        fig.tight_layout(rect=(.025,.02,.98,.87))
        path=output/f'{name}.png'
        fig.savefig(path,dpi=150,facecolor='white')
        paths.append(path)
        plt.close(fig)

    dates=sorted({r['day'] for r in quality['daily']})
    daily={(r['day'],r['event_type']):r['events'] for r in quality['daily']}
    x=[dt.date.fromisoformat(day) for day in dates]
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    axes[0].plot(x,[daily.get((day,'view'),0)/1e6 for day in dates],color=BLUE,marker='.',linewidth=1.8)
    axes[0].set(title='Просмотры',ylabel='Млн событий в день',ylim=(0,None))
    for kind,color,style,label in [('cart',BLUE,'-','Корзина'),('purchase',ORANGE,'--','Покупка')]:
        axes[1].plot(x,[daily.get((day,kind),0)/1e3 for day in dates],color=color,linestyle=style,label=label,linewidth=1.8)
    axes[1].set(title='Корзина и покупка',ylabel='Тысяч событий в день',ylim=(0,None));axes[1].legend(frameon=False)
    for ax in axes:
        ax.tick_params(axis='x',rotation=35);ax.grid(axis='y',alpha=.15)
    finish(fig,'01_daily','События по дням','REES46 Multi-category · весь октябрь 2019 · UTC · строки действий, не показы или заказы')

    fig,ax=plt.subplots(figsize=(11,5))
    fields=list(quality['missing']);values=[100*quality['missing'][f]/quality['summary']['rows'] for f in fields]
    ax.barh(fields[::-1],values[::-1],color=BLUE,edgecolor=INK,linewidth=.5)
    ax.set(xlabel='Доля всех событий, %',xlim=(0,max(values)*1.2))
    for y,value in enumerate(values[::-1]):ax.text(value+.3,y,f'{value:.2f}%',va='center',fontsize=10)
    finish(fig,'02_missing','Пропуски по столбцам','Доля от 42,45 млн строк · category_code — читаемая подпись; category_id присутствует во всех строках')

    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,table,key,total,title in [
        (axes[0],users['user_event_bins'],'users',users['user_summary']['users'],'События на пользователя'),
        (axes[1],users['pre_purchase_user_history'],'purchase_rows',users['warm_purchase_rows']['purchase_rows'],'История перед покупкой')]:
        bin_key='event_bin' if key=='users' else 'prior_event_bin'
        labels=[r[bin_key].split(': ',1)[1] for r in table];values=[100*r[key]/total for r in table]
        ax.bar(labels,values,color=BLUE,edgecolor=INK,linewidth=.5)
        ax.set(title=title,ylabel='Доля пользователей, %' if key=='users' else 'Доля purchase-строк, %',ylim=(0,max(values)*1.2))
        for i,v in enumerate(values):ax.text(i,v+.4,f'{v:.1f}',ha='center',fontsize=9)
    finish(fig,'03_history','Объём наблюдаемой истории','Разные знаменатели в панелях · справа только события строго раньше покупки; та же секунда исключена')

    fig,ax=plt.subplots(figsize=(11,5.5))
    rows=quality['categories'][::-1]
    ax.barh([r['category'] for r in rows],[r['events']/1e6 for r in rows],color=BLUE,edgecolor=INK,linewidth=.5)
    ax.set(xlabel='Млн событий',xlim=(0,None))
    finish(fig,'04_categories','События по верхним категориям','Топ-12 верхних уровней category_code · [unknown] — отсутствующая читаемая категория')

    fig,ax=plt.subplots(figsize=(11,5.3))
    cutoffs=sorted({r['cutoff'] for r in users['cutoff_purchase_coverage']});bottom=np.zeros(len(cutoffs))
    labels=['08 октября','15 октября','22 октября']
    styles=[(False,False,'Новый user / новый item','#BFC4C9','..'),
        (False,True,'Новый user / известный item',GOLD,'//'),
        (True,False,'Известный user / новый item',ORANGE,'xx'),
        (True,True,'Известный user / известный item',BLUE,'')]
    for ku,ki,label,color,hatch in styles:
        fractions=[]
        for cutoff in cutoffs:
            rows=[r for r in users['cutoff_purchase_coverage'] if r['cutoff']==cutoff]
            total=sum(r['distinct_purchased_pairs'] for r in rows)
            number=sum(r['distinct_purchased_pairs'] for r in rows if r['known_user']==ku and r['known_item']==ki)
            fractions.append(100*number/total)
        ax.bar(labels,fractions,bottom=bottom,color=color,hatch=hatch,edgecolor=INK,linewidth=.6,label=label)
        if ku and ki:
            for i,v in enumerate(fractions):ax.text(i,bottom[i]+v/2,f'{v:.1f}%',ha='center',va='center',color='white',weight='bold')
        bottom+=fractions
    ax.set(ylabel='Доля уникальных купленных user–item пар, %',ylim=(0,100))
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.09),ncol=2,frameon=False,fontsize=9)
    finish(fig,'05_cutoffs','Известные пользователи и товары на срезах','Покупки в следующие 7 дней · «известный» = первое наблюдение строго до среза · не candidate recall')

    delay=users['view_to_purchase_delay'];matched=delay['matched_purchase_keys']
    nums=[delay['matched_within_one_hour'],delay['matched_within_one_day']-delay['matched_within_one_hour'],
        delay['matched_within_seven_days']-delay['matched_within_one_day'],matched-delay['matched_within_seven_days']]
    fig,ax=plt.subplots(figsize=(11,5))
    vals=[100*n/matched for n in nums]
    ax.bar(['До 1 часа','1–24 часа','1–7 дней','Больше 7 дней'],vals,color=BLUE,edgecolor=INK,linewidth=.5)
    ax.set(ylabel='Доля matched purchase-ключей, %',ylim=(0,110))
    for i,(v,n) in enumerate(zip(vals,nums)):ax.text(i,v+1.5,f'{v:.2f}%\n{n:,}',ha='center',fontsize=10)
    finish(fig,'06_delays','Задержка от последнего предыдущего просмотра',
        f"Matched {matched:,} из {delay['purchase_keys']:,} purchase-ключей · строго прошлый view · не конверсия просмотров")

    kinds=['view','cart','purchase'];matrix=np.zeros((3,3),dtype=int)
    for row in quality.get('transitions',[]):
        if row['previous_kind'] in kinds and row['kind'] in kinds:
            matrix[kinds.index(row['previous_kind']),kinds.index(row['kind'])]=row['timestamp_bucket_pairs']
    shares=100*matrix/np.maximum(matrix.sum(axis=1,keepdims=True),1)
    fig,ax=plt.subplots(figsize=(9,5.5))
    ax.imshow(shares,cmap='Blues',vmin=0,vmax=100)
    ax.set_xticks(range(3),kinds);ax.set_yticks(range(3),kinds)
    ax.set(xlabel='Следующий соседний timestamp-блок',ylabel='Предыдущий блок')
    for i in range(3):
        for j in range(3):ax.text(j,i,f'{shares[i,j]:.1f}%\n{matrix[i,j]:,}',ha='center',va='center',color='white' if shares[i,j]>50 else INK)
    finish(fig,'07_transitions','Переходы между действиями внутри сессии',
        'Нормировка по строке · ключ сессии (user, session) · неоднозначные секунды исключают соседнюю пару')
    return paths
