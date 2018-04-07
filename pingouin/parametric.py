# Author: Raphael Vallat <raphaelvallat9@gmail.com>
# Date: April 2018
import numpy as np
import pandas as pd

__all__ = ["gzscore", "test_normality", "test_homoscedasticity", "test_dist",
           "test_sphericity", "rm_anova", "anova", "mixed_anova"]


def gzscore(x):
    """Geometric standard (Z) score.

    Geometric Z-score are better than arithmetic z-scores when the data
    comes from a log-normal or chi-squares distribution.

    Parameters
    ----------
    x : array_like
        Array of raw values

    Returns
    -------
    gzscore : array_like
        Array of geometric z-scores (same shape as x)
    """
    from scipy.stats import gmean
    # Geometric mean
    geo_mean = gmean(x)
    # Geometric standard deviation
    gstd = np.exp(np.sqrt(np.sum((np.log(x / geo_mean))**2) / (len(x) - 1)))
    # Geometric z-score
    return np.log(x / geo_mean) / np.log(gstd)

# MAIN FUNCTIONS


def test_normality(*args, alpha=.05):
    """Test the normality of one or more array.

    Parameters
    ----------
    sample1, sample2,... : array_like
        Array of sample data. May be different lengths.

    Returns
    -------
    normal : boolean
        True if x comes from a normal distribution.
    p : float
        P-value.
    """
    from scipy.stats import shapiro
    # Handle empty input
    for a in args:
        if np.asanyarray(a).size == 0:
            return np.nan, np.nan

    k = len(args)
    p = np.zeros(k)
    normal = np.zeros(k, 'bool')
    for j in range(k):
        _, p[j] = shapiro(args[j])
        normal[j] = True if p[j] > alpha else False

    if k == 1:
        normal = bool(normal)
        p = float(p)

    return normal, p


def test_homoscedasticity(*args, alpha=.05):
    """Test equality of variance.

    If data are normally distributed, uses Bartlett (1937).
    If data are not-normally distributed, uses Levene (1960).

    Parameters
    ----------
    sample1, sample2,... : array_like
        Array of sample data. May be different lengths.

    Returns
    -------
    equal_var : boolean
        True if data have equal variance.
    p : float
        P-value.
    """
    from scipy.stats import levene, bartlett
    # Handle empty input
    for a in args:
        if np.asanyarray(a).size == 0:
            return np.nan, np.nan

    k = len(args)
    if k < 2:
        raise ValueError("Must enter at least two input sample vectors.")

    # Test normality of data
    normal, _ = test_normality(*args)
    if np.count_nonzero(normal) != normal.size:
        # print('Data are not normally distributed. Using Levene test.')
        _, p = levene(*args)
    else:
        _, p = bartlett(*args)

    equal_var = True if p > alpha else False
    return equal_var, p


def test_dist(*args, dist='norm'):
    """Anderson-Darling test of distribution.

    Parameters
    ----------
    sample1, sample2,... : array_like
        Array of sample data. May be different lengths.
    dist : string
        Distribution ('norm', 'expon', 'logistic', 'gumbel')

    Returns
    -------
    from_dist : boolean
        True if data comes from this distribution.
    """
    from scipy.stats import anderson
    # Handle empty input
    for a in args:
        if np.asanyarray(a).size == 0:
            return np.nan, np.nan

    k = len(args)
    from_dist = np.zeros(k, 'bool')
    sig_level = np.zeros(k)
    for j in range(k):
        st, cr, sig = anderson(args[j], dist=dist)
        from_dist[j] = True if (st > cr).any() else False
        sig_level[j] = sig[np.argmin(np.abs(st - cr))]

    if k == 1:
        from_dist = bool(from_dist)
        sig_level = float(sig_level)
    return from_dist, sig_level


def test_sphericity(X, alpha=.05):
    """Mauchly's test for sphericity

    https://www.mathworks.com/help/stats/mauchlys-test-of-sphericity.html

    Warning: results can slightly differ than R or Matlab. If you can,
    always double-check your results.

    Parameters
    ----------
    X : array_like
        Data array of shape (n_observations, n_repetitions)
    alpha : float, optional
        Significance level

    Returns
    -------
    sphericity : boolean
        True if data have the sphericity property.
    W : float
        Mauchly's W statistic
    chi_sq : float
        Chi-square statistic
    ddof : int
        Degrees of freedom
    p : float
        P-value.
    """
    from scipy.stats import chi2
    n = X.shape[0]

    # Compute the covariance matrix
    S = np.cov(X, rowvar=0)
    p = S.shape[1]
    d = p - 1

    # Orthonormal contrast matrix
    C = np.array(np.triu(np.ones((p, d))), order='F')
    C.reshape(-1, order='F')[1::p + 1] = -np.arange(d)
    C, _ = np.linalg.qr(C)
    d = C.shape[1]
    T = C.T.dot(S).dot(C)

    # Mauchly's statistic
    W = np.linalg.det(T) / (np.trace(T) / (p - 1))**d

    # Chi-square statistic
    nr = n - np.linalg.matrix_rank(X)
    dd = 1 - (2 * d**2 + d + 2) / (6 * d * nr)
    chi_sq = -np.log(W) * dd * nr
    ddof = d * (d + 1) / 2 - 1
    pval = chi2.sf(chi_sq, ddof)
    sphericity = True if pval > alpha else False

    return sphericity, W, chi_sq, ddof, pval


def ss(grp, type='a'):
    """Sums of squares"""
    return np.sum(grp.sum()**2) if type == 'a' else grp.sum().sum()**2


def rm_anova(dv=None, within=None, data=None, correction='auto',
             remove_na=False, full_table=False):
    """Compute one-way repeated measures ANOVA from a pandas DataFrame.

    Tested against mne.stats.f_mway_rm and ez R package.

    Parameters
    ----------
    dv : string
        Name of column containing the dependant variable.
    within : string
        Name of column containing the within factor.
    data : pandas DataFrame
        DataFrame
    correction : string or boolean
        If True, return Greenhouse-Geisser corrected p-value.
        If 'auto' (default), compute Mauchly's test of sphericity to determine
        whether the p-values needs to be corrected.
    remove_na : boolean
        If True, automatically remove from the analysis subjects with one or
        more missing values:

        Ss    x1       x2       x3
        --    ---      ----     ---
        1     5.0      4.2      nan

        If true, Ss 1 will be removed from the ANOVA because of the x3 missing
        values. If False, the two non-missing values will be included in the
        analysis.
    full_table : boolean
        If True, return a full ANOVA table

    Returns
    -------
    aov : DataFrame
        ANOVA summary
    """
    from scipy.stats import f
    rm = list(data[within].unique())
    n_rm = len(rm)
    N = data[dv].size

    # Groupby
    grp_with = data.groupby(within)[dv]
    n_obs = int(data.groupby(within)[dv].count().max())

    # Sums of squares
    sstime = ss(grp_with) / n_obs - ss(grp_with, 'b') / N
    ssw = np.zeros(n_rm)
    for i, (name, group) in enumerate(grp_with):
        ssw[i] = np.sum((group - group.mean())**2)
    sswithin = np.sum(ssw)

    # Calculating SSsubjects and SSerror
    data['Subj'] = np.tile(np.arange(n_obs), n_rm)
    grp_subj = data.groupby('Subj')[dv]
    sssubj = n_rm * np.sum((grp_subj.mean() - grp_subj.mean().mean())**2)
    sserror = sswithin - sssubj

    # Calculate degrees of freedom, F- and p-values
    ddof1 = n_rm - 1
    ddof2 = ddof1 * (n_obs - 1)
    mserror = sserror / (ddof2 / ddof1)
    fval = sstime / mserror
    p_unc = f(ddof1, ddof2).sf(fval)

    # Calculating partial eta-square
    # Similar to (fval * ddof1) / (fval * ddof1 + ddof2)
    np2 = sstime / (sstime + sserror)

    # Reshape and remove NAN for sphericity estimation and correction
    data_pivot = data.pivot(index='Subj', columns=within, values=dv).dropna()

    # Compute sphericity using Mauchly's test
    # Sphericity assumption only applies if there are more than 2 levels
    if correction == 'auto' or correction == True and n_rm >= 3:
        sphericity, W_mauchly, chi_sq_mauchly, ddof_mauchly, \
        p_mauchly = test_sphericity(data_pivot.as_matrix(), alpha=.05)

        if correction == 'auto':
            correction = True if not sphericity else False
    else:
        correction = False

    # If required, apply Greenhouse-Geisser correction for sphericity
    if correction:
        # Compute covariance matrix
        v = data_pivot.cov().as_matrix()
        eps = np.trace(v) ** 2 / ddof1 * np.sum(np.sum(v * v, axis=1))
        corr_ddof1, corr_ddof2 = [np.maximum(d * eps, 1.) for d in
                                  (ddof1, ddof2)]
        p_corr = f(corr_ddof1, corr_ddof2).sf(fval)

    # Create output dataframe
    if not full_table:
        aov = pd.DataFrame({'Source': within,
                            'ddof1': ddof1,
                            'ddof2': ddof2,
                            'F': fval,
                            'p-unc': p_unc,
                            'np2': np2
                            }, index=[0])
        if correction:
            aov['p-GG-corr'] = p_corr
            aov['W-Mauchly'] = W_mauchly
            aov['X2-Mauchly'] = chi_sq_mauchly
            aov['DF-Mauchly'] = ddof_mauchly
            aov['p-Mauchly'] = p_mauchly
            aov['sphericity'] = sphericity

        col_order = ['Source', 'ddof1', 'ddof2', 'F', 'p-unc',
                    'p-GG-corr', 'np2', 'sphericity','W-Mauchly', 'X2-Mauchly',
                    'DF-Mauchly', 'p-Mauchly']
    else:
        aov = pd.DataFrame({'Source': [within, 'Error'],
                            'SS': [sstime, sserror],
                            'DF': [ddof1, ddof2],
                            'MS': [sstime / ddof1, sserror / ddof2],
                            'F': [fval, np.nan],
                            'p-unc': [p_unc, np.nan],
                            'np2': [np2, np.nan]
                            })
        if correction:
            aov['p-GG-corr'] = [p_corr, np.nan]
            aov['W-Mauchly'] = [W_mauchly, np.nan]
            aov['X2-Mauchly'] = [chi_sq_mauchly, np.nan]
            aov['DF-Mauchly'] = np.array([ddof_mauchly, 0], 'int')
            aov['p-Mauchly'] = [p_mauchly, np.nan]
            aov['sphericity'] = [sphericity, np.nan]

        col_order = ['Source', 'SS', 'DF', 'MS', 'F', 'p-unc', 'p-GG-corr',
                     'np2', 'sphericity','W-Mauchly', 'X2-Mauchly',
                     'DF-Mauchly', 'p-Mauchly']

    aov = aov.reindex(columns=col_order)
    aov.dropna(how='all', axis=1, inplace=True)
    return aov


def anova(dv=None, between=None, data=None, full_table=False):
    """Compute one-way ANOVA from a pandas DataFrame.

    Tested against ez R package.

    Parameters
    ----------
    dv : string
        Name of column containing the dependant variable.
    between : string
        Name of column containing the between factor.
    data : pandas DataFrame
        DataFrame
    full_table : boolean
        If True, return a full ANOVA table

    Returns
    -------
    aov : DataFrame
        ANOVA summary
    """
    from scipy.stats import f
    groups = list(data[between].unique())
    n_groups = len(groups)
    N = data[dv].size

    grp_betw = data.groupby(between)[dv]
    n_obs = grp_betw.count().as_matrix()

    # Sums of squares
    grandmean = grp_betw.mean().mean()
    ssb, ssw = np.zeros(n_groups), np.zeros(n_groups)
    for i, (name, group) in enumerate(grp_betw):
        ssb[i] = group.count() * np.sum((group.mean() - grandmean)**2)
        ssw[i] = np.sum((group - group.mean())**2)

    ssbetween = np.sum(ssb)
    sswithin = np.sum(ssw)

    # Calculate degrees of freedom, F- and p-values
    ddof1 = n_groups - 1
    msbetween = ssbetween / ddof1
    ddof2 = N - n_groups
    mswithin = sswithin / ddof2
    fval = msbetween / mswithin
    p_unc = f(ddof1, ddof2).sf(fval)

    # Calculating partial eta-square
    # Similar to (fval * ddof1) / (fval * ddof1 + ddof2)
    np2 = ssbetween / (ssbetween + sswithin)

    # Create output dataframe
    if not full_table:
        aov = pd.DataFrame({'Source': between,
                            'ddof1': ddof1,
                            'ddof2': ddof2,
                            'F': fval,
                            'p-unc': p_unc,
                            'np2': np2
                            }, index=[0])

        col_order = ['Source', 'ddof1', 'ddof2', 'F', 'p-unc', 'np2']
    else:
        aov = pd.DataFrame({'Source': [between, 'Within'],
                            'SS': [ssbetween, sswithin],
                            'DF': [ddof1, ddof2],
                            'MS': [msbetween, mswithin],
                            'F': [fval, np.nan],
                            'p-unc': [p_unc, np.nan],
                            'np2': [np2, np.nan]
                            })
        col_order = ['Source', 'SS', 'DF', 'MS', 'F', 'p-unc', 'np2']

    aov = aov.reindex(columns=col_order)
    aov.dropna(how='all', axis=1, inplace=True)
    return aov


def mixed_anova(dv=None, within=None, between=None, data=None,
                correction='auto', remove_na=False):
    """Compute one-way ANOVA from a pandas DataFrame.

    Tested against ez R package.

    Parameters
    ----------
    dv : string
        Name of column containing the dependant variable.
    between : string
        Name of column containing the between factor.
    data : pandas DataFrame
        DataFrame
    correction : string or boolean
        If True, return Greenhouse-Geisser corrected p-value.
        If 'auto' (default), compute Mauchly's test of sphericity to determine
        whether the p-values needs to be corrected.
    remove_na : boolean
        If True, automatically remove from the analysis subjects with one or
        more missing values:

        Ss    x1       x2       x3
        --    ---      ----     ---
        1     5.0      4.2      nan

        If true, Ss 1 will be removed from the ANOVA because of the x3 missing
        values. If False, the two non-missing values will be included in the
        analysis.

    Returns
    -------
    aov : DataFrame
        ANOVA summary
    """
    from scipy.stats import f
    N = data[dv].size

    # SUMS OF SQUARES
    # Time effect
    grp_with = data.groupby(within)[dv]
    n_obs = grp_with.count().max()
    n_rm = grp_with.count().count()
    sstime = ss(grp_with) / n_obs - ss(grp_with, 'b') / N

    # Between effect
    grp_betw = data.groupby(between)[dv]
    ssbetween = ss(grp_betw) / grp_betw.count().max() - ss(grp_betw, 'b') / N

    # Within-group effect
    grp = data.groupby([between, within])[dv]
    n_group = grp.count().count()
    n_obs = grp.count().max()
    ssa = grp.apply(lambda x: x**2).sum()
    sswg = ssa - ss(grp) / n_obs
    sstotal = ssa - ss(grp, 'b') / N

    # Interaction
    ssinter = sstotal - (sswg + sstime + ssbetween)

    # DEGREES OF FREEDOM
    dftime = grp_with.count().count() - 1
    dfbetween = grp_betw.count().count() - 1
    dfwg = N - grp.count().count()
    dftotal = N - 1
    dfinter = dftime * dfbetween

    # MEAN SQUARES
    mstime = sstime / dftime
    msbetween = ssbetween / dfbetween
    mswg = sswg / dfwg
    msinter = ssinter / dfinter

    # F VALUES
    ftime = mstime / mswg
    fbetween = msbetween / mswg
    finter = msinter / mswg

    # P-values
    ptime = f(dftime, dfwg).sf(ftime)
    pbetween = f(dfbetween, dfwg).sf(fbetween)
    pinter = f(dfinter, dfwg).sf(finter)

    # Effects sizes
    npsq_between = fbetween * dfbetween / (fbetween * dfbetween + dfwg)
    npsq_time = ftime * dftime / (ftime * dftime + dfwg)
    npsq_inter = ssinter / (ssinter + sswg)

    # Stats table
    aov = pd.DataFrame({'Source': [between, within, 'Interaction'],
                        'SS': [ssbetween, sstime, ssinter],
                        'DF': [dfbetween, dftime, dfinter],
                        'MS': [msbetween, mstime, msinter],
                        'F': [fbetween, ftime, finter],
                        'p-unc': [pbetween, ptime, pinter],
                        'np2': [npsq_between, npsq_time, npsq_inter]
                        })
    col_order = ['Source', 'SS', 'DF', 'MS', 'F', 'p-unc', 'np2']

    aov = aov.reindex(columns=col_order)
    aov.dropna(how='all', axis=1, inplace=True)
    return aov
