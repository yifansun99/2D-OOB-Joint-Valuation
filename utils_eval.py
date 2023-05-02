import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import precision_recall_curve, auc, ndcg_score, f1_score
from ensemble_DV_core_original import RandomForestClassifierDV_original, RandomForestRegressorDV_original


from sklearn.cluster import KMeans
from scipy.integrate import simpson
from scipy.stats import spearmanr, rankdata, ttest_ind, norm, weightedtau
import xgboost as xgb
import tqdm

def noisy_detection_experiment(value_dict, noisy_index):
    noisy_score_dict=dict()
    for key in value_dict.keys():
        noisy_score_dict[key]=noisy_detection_core(value_dict[key], noisy_index)

    noisy_dict={'Meta_Data': ['Recall', 'Kmeans_label'],
                'Results': noisy_score_dict}
    return noisy_dict

def mask_detection_experiment(value_dict, mask_index):
    mask_score_dict=dict()
    for key in value_dict.keys():
        mask_score_dict[key]=noisy_detection_core(np.abs(value_dict[key]), mask_index)

    mask_dict={'Meta_Data': ['Recall', 'Kmeans_label'],
                'Results': mask_score_dict}
    return mask_dict

def kmeans_smaller_cluster_indices_row(matrix, error_row_index):
    binary_matrix = np.zeros_like(matrix)
    if isinstance(error_row_index,np.ndarray):
        to_enumerate = error_row_index
    else:
        raise ValueError('You should input error_row_index')
        # to_enumerate = range(matrix.shape[0])
    for i in to_enumerate:
        row = matrix[i, :]
        kmeans = KMeans(n_clusters=2, random_state=0, n_init='auto').fit(row.reshape(-1, 1))
        smaller_cluster_idx = np.where(kmeans.labels_ == np.argmin(kmeans.cluster_centers_))[0]
        binary_matrix[i, smaller_cluster_idx] = 1
    return binary_matrix

def get_min_k_indices(matrix, k, error_row_index): 
    binary_matrix = np.zeros_like(matrix)
    if isinstance(error_row_index,np.ndarray):
        to_enumerate = error_row_index
    else:
        raise ValueError('You should input error_row_index')
        # to_enumerate = range(matrix.shape[0])
    for i in to_enumerate:
        row_data = matrix[i]
        sorted_indices = np.argsort(row_data)
        binary_matrix[i, sorted_indices[:k]] = 1
    return binary_matrix

def error_detection_experiment(value_dict, error_index, error_row_index):
    error_score_dict=dict()
    for key in value_dict.keys():
        error_score_dict[key]=error_detection_core(value_dict[key], error_index, error_row_index, method='k_means')
        error_score_dict[key].extend(error_detection_core(value_dict[key], error_index, error_row_index, method='min_k'))
    error_dict={'Meta_Data': ['Kmeans_label','Kmeans_matrix','min_k_label','min_k_matrix'],
                'Results': error_score_dict}
    return error_dict
    
def error_detection_core(value, error_index, error_row_index, method='min_k'):
    # error_rate = sum(error_index[0])/len(error_index[0])
    if method == 'min_k':
        prediction_row = get_min_k_indices(value, max(error_index.sum(axis=1)), error_row_index)
    elif method == 'k_means':
        prediction_row = kmeans_smaller_cluster_indices_row(value, error_row_index)
    else:
        raise NotImplementedError('Not implemented yet!')

    ground_truth_flat = error_index.flatten()
    prediction_row_flat = prediction_row.flatten()
    
    # using kmeans label
    f1_kmeans_label_row = f1_score(ground_truth_flat, prediction_row_flat, average='binary')  # Use 'binary' averaging for binary classification
    return [f1_kmeans_label_row, prediction_row]    
 
def rank_experiment(value_dict, beta_true):
    rank_score_dict=dict()
    for key in value_dict.keys():
        rank_score_dict[key]=(corr_evaluation_core(value_dict[key], beta_true),
                              # ndcg_evaluation_core(value_dict[key], beta_true),
                              # weightedtau(np.abs(beta_true), np.abs(value_dict[key]))[0]
                              )
    rank_dict={'Meta_Data': ['Corr'
                             # ,'NDCG'
                             # ,'Tau'
                             ],
                'Results': rank_score_dict}
    return rank_dict

def ndcg_evaluation_core(value, beta_true):
    return ndcg_score(np.abs(beta_true).reshape(-1), np.abs(value).reshape(-1))

def rankcorr(attrA, attrB, k):
    # rank features (accounting for ties)
    # rankdata gives rank1 for smallest # --> we want rank1 for largest # (aka # with largest magnitude)
    all_feat_ranksA = rankdata(-np.abs(attrA), method='ordinal')
    all_feat_ranksB = rankdata(-np.abs(attrB), method='ordinal')

    rho = (spearmanr(all_feat_ranksA[all_feat_ranksA <= k], all_feat_ranksB[all_feat_ranksA <= k])[0] + 
                  spearmanr(all_feat_ranksA[all_feat_ranksB <= k], all_feat_ranksB[all_feat_ranksB <= k])[0])/2
    return rho

def corr_evaluation_core(value, beta_true):
    attrA = np.abs(beta_true).reshape(-1)
    attrB = np.abs(value).reshape(-1)
    return rankcorr(attrA, attrB, k = (beta_true != 0).sum())

def noisy_detection_core(value, noisy_index):
    # without kmeans algorithm (but requires prior knowledge of the number of noise labels)
    index_of_small_values=np.argsort(value)[:len(noisy_index)]
    recall=len([ind for ind in index_of_small_values if ind in noisy_index])/len(noisy_index)
    
    # using kmeans label
    kmeans=KMeans(n_clusters=2, random_state=0, n_init='auto').fit(value.reshape(-1, 1))
    guess_index=np.where(kmeans.labels_ == np.argmin(kmeans.cluster_centers_))[0]
    f1_kmeans_label=compute_f1_score_by_set(noisy_index, guess_index)

    return [recall, f1_kmeans_label] 

def compute_f1_score_by_set(list_a, list_b):
    '''
    Comput F1 score for noisy detection task
    list_a : true flipped data points
    list_b : predicted flipped data points
    '''
    n_a, n_b=len(list_a), len(list_b)
    
    # among A, how many B's are selected
    n_intersection=len(set(list_b).intersection(list_a))
    recall=n_intersection/(n_a+1e-16)
    # among B, how many A's are selected
    precision=n_intersection/(n_b+1e-16)
    
    if recall > 0 and precision > 0:
        f1_score=1/((1/recall + 1/precision)/2)
    else:
        f1_score=0.
    return f1_score
    
def point_removal_experiment(value_dict, X, y, X_test, y_test, problem='clf'):
    removal_ascending_dict=dict()
    for key in value_dict.keys():
        removal_ascending_dict[key]=point_removal_core(X, y, X_test, y_test, value_dict[key], ascending=True, problem=problem)
    random_array=point_removal_core(X, y, X_test, y_test, 'Random', problem=problem)
    removal_ascending_dict['Random']=random_array
    return {'ascending↑':removal_ascending_dict}

def point_removal_core(X, y, X_test, y_test, value_list, ascending=True, problem='clf'):
    n_sample=len(X)
    if value_list == 'Random':
        sorted_value_list=np.random.permutation(n_sample) 
    else:
        if ascending is True:
            sorted_value_list=np.argsort(value_list) # ascending order. low to high.
    
    accuracy_list=[]
    n_period = min(n_sample//100, 5) # we add 1% at each time
    for percentile in tqdm.tqdm(range(0, n_sample//5, n_period)):
        '''
        We repeatedly remove 5% of entire data points at each step.
        The data points whose value belongs to the lowest group are removed first.
        The larger, the better
        '''
        sorted_value_list_tmp=sorted_value_list[percentile:]
        if problem == 'clf':
            try:
                clf=RandomForestClassifierDV_original(n_estimators=1000, n_jobs=-1)
                clf.fit(X[sorted_value_list_tmp], y[sorted_value_list_tmp])
                model_score=clf.score(X_test, y_test)
            except:
                # if y[sorted_value_list_tmp] only has one class
                model_score=np.mean(np.mean(y[sorted_value_list_tmp])==y_test)
        else:
            try:
                model=RandomForestRegressorDV_original(n_estimators=1000, n_jobs=-1) 
                model.fit(X[sorted_value_list_tmp], y[sorted_value_list_tmp])
                model_score=model.score(X_test, y_test)
            except:
                # if y[sorted_value_list_tmp] only has one class
                model_score=0

        accuracy_list.append(model_score)
        
    return accuracy_list


def feature_removal_experiment(value_dict, X, y, X_test, y_test, random=True):
    removal_dict = dict()
    for key in value_dict.keys():
        removal_dict[key]=feature_removal_core(X, y, X_test, y_test, value_dict[key])
    if random:
        random_array=feature_removal_core(X, y, X_test, y_test, 'Random')
        removal_dict['Random']=random_array
    return {'removal':removal_dict} #the smaller the better

def feature_removal_core(X, y, X_test, y_test, value_list):
    d_sample=X.shape[1]
    if value_list == 'Random':
        sorted_value_list=np.random.permutation(d_sample) 
    else:
        sorted_value_list=np.argsort(-value_list) # descending order. high to low.
    
    accuracy_list=[]
    for n_remove in tqdm.tqdm(range(1, d_sample)):
        sorted_value_list_tmp=sorted_value_list[n_remove:]
        clf=RandomForestClassifierDV_original(n_estimators=1000, n_jobs=-1)
        clf.fit(X[:,sorted_value_list_tmp], y)
        model_score=clf.score(X_test[:,sorted_value_list_tmp], y_test)

        accuracy_list.append(model_score)
        
    return accuracy_list,simpson(accuracy_list, dx = 1),simpson(accuracy_list[:max(5,int(len(accuracy_list)//5))], dx = 1)



def feature_loo_experiment(value_dict, X, y, X_test, y_test, random=True):
    loo_dict = dict()
    d_sample=X.shape[1]
    loo_score = np.zeros(d_sample)
    for d in tqdm.tqdm(range(d_sample)):
        tmp_scores = []
        for _ in range(3):
            clf=RandomForestClassifierDV_original(n_estimators=1000, n_jobs=-1)
            clf.fit(np.delete(X, d, axis=1), y)
            tmp_scores.append(clf.score(np.delete(X_test, d, axis=1), y_test))
        loo_score[d]=np.mean(tmp_scores)
    rank_loo = rankdata(loo_score, method='ordinal')
    for key in value_dict.keys():
        rank_value = rankdata(-value_dict[key], method='ordinal')
        loo_dict[key]=spearmanr(rank_loo,rank_value)[0]
    return {'loo_Corr':loo_dict,'loo_score':loo_score} 










def array_not_in_indices(arr, indices):
    return np.array([arr[i] for i in range(len(arr)) if i not in indices])
    
def generate_data(n, input_dim, beta_true, mislabel = True, rho = 0):
    if rho != 0:
        U_cov = np.diag((1-rho)*np.ones(input_dim))+rho
        U_mean = np.zeros(input_dim)
        data = np.random.multivariate_normal(U_mean, U_cov, n)
    else:
        data = np.random.normal(size=(n,input_dim))
    p_true = np.exp(data.dot(beta_true))/(1.+np.exp(data.dot(beta_true)))
    target = np.random.binomial(n=1, p=p_true).reshape(-1)
    
    if mislabel:
        target = 1 - target
    return data, target

def ecdf(arr):
    n = len(arr)
    x = np.sort(arr)
    y = np.arange(1, n+1) / n
    return x, y

def find_quantile_ecdf(arr, num):
    x, y = ecdf(arr)
    index = np.searchsorted(x, num)
    if index == 0:
        return 0.0
    elif index == len(x):
        return 1.0
    else:
        left_x, right_x = x[index-1], x[index]
        left_y, right_y = y[index-1], y[index]
        slope = (right_y - left_y) / (right_x - left_x)
        quantile = left_y + slope * (num - left_x)
        return quantile
    
def mean_ci(data, confidence=0.95):
    sample_mean = np.mean(data)
    sample_std = np.std(data, ddof=1)

    standard_error = sample_std / np.sqrt(len(data))

    alpha = 1 - confidence
    z_critical = norm.ppf(1 - alpha / 2)

    lower_bound = sample_mean - z_critical * standard_error
    upper_bound = sample_mean + z_critical * standard_error

    return lower_bound, upper_bound

def evalution_new(oob, noisy_index, model, X_y, beta_true, rho):
    n = X_y.shape[0]
    input_dim = X_y.shape[1]-1
    labeled_X, labeled_y = generate_data(n, input_dim, beta_true, mislabel = False, rho = rho)
    mislabeled_X, mislabeled_y = generate_data(n, input_dim, beta_true, mislabel = True, rho = rho)

    labeled_data = xgb.DMatrix(np.concatenate((labeled_X,labeled_y.reshape(-1,1)), axis=1))
    mislabeled_data = xgb.DMatrix(np.concatenate((mislabeled_X,mislabeled_y.reshape(-1,1)), axis=1))
    
    assert(labeled_data.num_col() == input_dim+1)
    assert(mislabeled_data.num_col() == input_dim+1)

    new_clean = model.predict(labeled_data)
    new_noisy = model.predict(mislabeled_data)
    
    oob_clean = array_not_in_indices(oob, noisy_index)
    oob_noisy = oob[noisy_index]
    
    assert(len(oob_clean) == len(oob)-len(noisy_index))
    assert(len(oob_noisy) == len(noisy_index))

    new_clean_quantile = np.array([find_quantile_ecdf(oob,i) for i in new_clean])
    new_noisy_quantile = np.array([find_quantile_ecdf(oob,i) for i in new_noisy])
    
    return {
        'oob_clean_mean':oob_clean.mean(),
        'oob_noisy_mean':oob_noisy.mean(),
        'oob_clean_CI':mean_ci(oob_clean),
        'oob_noisy_CI':mean_ci(oob_noisy),
        'oob_ttest':ttest_ind(oob_clean,oob_noisy)[1],
        
        'new_clean_mean':new_clean.mean(),
        'new_noisy_mean':new_noisy.mean(),
        'new_clean_CI':mean_ci(new_clean),
        'new_noisy_CI':mean_ci(new_noisy),
        'new_ttest':ttest_ind(new_clean,new_noisy)[1],
        
        'new_clean_quantile_mean':new_clean_quantile.mean(),
        'new_noisy_quantile_mean':new_noisy_quantile.mean(),
        'new_clean_quantile_CI':mean_ci(new_clean_quantile),
        'new_noisy_quantile_CI':mean_ci(new_noisy_quantile),        
        'new_quantile_ttest':ttest_ind(new_clean_quantile,new_noisy_quantile)[1],
    }

