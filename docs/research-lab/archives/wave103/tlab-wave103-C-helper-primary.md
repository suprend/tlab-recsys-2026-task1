# Primary-source helper C — 2026-10-17

**NDCG.** [Ravikumar–Tewari–Yang, AISTATS 2011](https://proceedings.mlr.press/v15/ravikumar11a/ravikumar11a.pdf), §2, §3.1, Lemma 4 / Corollary 5, pp.619–621:

\[
f(X)\rightsquigarrow E[G(R)/\|G(R)\|_D\mid X]\quad\mu\text{-a.s.}
\]

Здесь \(\|G(R)\|_D=Z(R)=\max_\pi\sum_jG(R_j)/F(\pi(j))\), то есть IDCG; \(s\rightsquigarrow v\) означает \(v_i>v_j\Rightarrow s_i>s_j\). Scope: фиксированное число документов m, произвольное совместное условное распределение relevance-vector; монотонные gain/discount. Это характеристика Fisher/Bayes-optimal порядка, не обещание конечной выборочной эффективности. §3.2 прямо различает \(E[G(R)/Z(R)]\) и \(E[G(R)]\).

Алгебраическая специализация: binary \(G(y)=y\) даёт \(E[Y_i/IDCG(Y)\mid X]\). Замена на \(P(Y_i=1\mid X)\) требует отдельного обоснования; несколько покупок сами такого обоснования не дают. При нулевом IDCG нужна явно заданная конвенция.

**Pairwise.** [Duchi–Mackey–Jordan, ICML 2010 / Berkeley report](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2010/Archive/EECS-2010-56.pdf), §2.2, Eq.(9):
\[
W(p,\alpha)=\sum_{i\ne j}h_{ij}\phi(\alpha_i-\alpha_j),\quad h_{ij}=\sum_Gp_Gh(a^G_{ij}).
\]
Это ожидаемые веса пар при данном query/result-set. Следствие формулы: нормирование каждой query до усреднения задаёт \(E[w_{ij}(Y)/|P(Y)|\mid X]\); его нельзя без доказательства заменять отношением ожиданий. Статья здесь не доказывает NDCG-consistency query-normalized logistic.

**Фактически прочитано:** первая статья — §2, §3.1 целиком, вводный абзац §3.2; проверена страница621; вторая — начало §1 до Eq.(2), начало §2 Eq.(7–8), §2.2 только вводный абзац/Eq.(9). Полные статьи и приложения не прочитаны. Репозиторий/данные не читались; запусков, тестов, Git не было.
