from time import time
import numpy as np
import pickle
import shap
from collections import defaultdict
from sklearn import metrics

from ensemble_DV_core_subset import RandomForestClassifierDV_subset
from ensemble_DV_core_original import RandomForestClassifierDV_original
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

from data_approach import DataApproach
from feature_approach import FeatureApproach
import utils_eval
import knn_2d
import mc_2d


import warnings
warnings.filterwarnings("ignore")


class DataValuation(object):
    def __init__(self, X, y, X_val, y_val, 
                 X_test,y_test,problem, dargs):
        """
        Args:
            (X, y): (inputs, outputs) to be valued.
            (X_val, y_val): (inputs, outputs) to be used for utility evaluation.
            problem: "clf" 
            dargs: arguments of the experimental setting
        """
        self.X=X
        self.y=y
        self.X_val=X_val
        self.y_val=y_val
        self.X_test=X_test
        self.y_test=y_test
        self.problem=problem
        self.dargs=dargs
        self._initialize_instance()        
       
    def _initialize_instance(self):
        # intialize dictionaries
        self.experiment=self.dargs.get('experiment')
        self.run_id=self.dargs.get('run_id')
        self.n_tr=self.dargs.get('n_train')
        self.n_val=self.dargs.get('n_val')
        self.n_trees=self.dargs.get('n_trees')
        self.is_noisy=self.dargs.get('is_noisy')
        self.input_dim=self.dargs.get('input_dim')
        self.rho=self.dargs.get('rho')
        self.base=self.dargs.get('base')
        self.error_row_rate=self.dargs.get('error_row_rate')
        self.error_col_rate=self.dargs.get('error_col_rate')
        self.error_mech=self.dargs.get('error_mech')
        self.mask_ratio=self.dargs.get('mask_ratio')
        self.model_family=self.dargs.get('model_family')
        self.model_name=f'{self.n_tr}:{self.n_val}:{self.n_trees}:{self.is_noisy}'

        # set random seed
        np.random.seed(self.run_id)

        # create placeholders
        self.data_value_dict=defaultdict(list)
        self.feature_value_dict=defaultdict(list)
        self.df_value_dict=defaultdict(list)
        self.time_dict=defaultdict(list)
        self.noisy_detect_dict=defaultdict(list)
        self.mask_detect_dict=defaultdict(list)
        self.rank_dict=defaultdict(list)
        self.feature_removal_dict=defaultdict(list)
        self.cell_removal_dict=defaultdict(list)
        self.error_detect_dict=defaultdict(list)
        self.outlier_detect_dict=defaultdict(list)
        self.point_removal_dict=defaultdict(list)
        self.loo_dict=defaultdict(list)
            
    def compute_data_shap(self, loo_run=False, betashap_run=False):
        '''
        This function computes regular data valuation methods
        '''
        self.data_shap_engine=DataApproach(X=self.X, y=self.y, 
                                            X_val=self.X_val, y_val=self.y_val, 
                                            problem=self.problem, model_family=self.model_family)
        self.data_shap_engine.run(loo_run=loo_run, betashap_run=betashap_run)
        self._dict_update(self.data_shap_engine)

    def compute_feature_shap(self, data_oob_run=True, df_oob_run=True, subset_ratio_list=[0.25,0.5,0.75]):
        '''
        This function computes feature attribution and joint valuation methods
        '''
        self.feature_shap_engine=FeatureApproach(X=self.X, y=self.y, 
                                                 problem=self.problem, model_family=self.model_family,
                                                 n_trees=self.n_trees)
        self.feature_shap_engine.run(data_oob_run=data_oob_run,
                                     df_oob_run=df_oob_run,
                                     subset_ratio_list=subset_ratio_list)

        if data_oob_run:
            self.rf_model_original = self.feature_shap_engine.rf_model_original
        self._dict_update(self.feature_shap_engine)

    def _dict_update(self, engine):
        self.data_value_dict.update(engine.data_value_dict)
        self.feature_value_dict.update(engine.feature_value_dict)
        self.df_value_dict.update(engine.df_value_dict)
        self.time_dict.update(engine.time_dict)
        
    def prepare_baseline(self, SHAP_size=1000):
        # # base method: treeshap
        # print("Start: TreeSHAP computation")
        # time_init=time()
        # if SHAP_size == None:
        #     explainer = shap.TreeExplainer(self.rf_model_original)
        #     shap_values = explainer(self.X)
        # else:
        #     sample_X = self.X[np.random.choice(self.X.shape[0], size=SHAP_size, replace=False), :]
        #     explainer = shap.TreeExplainer(self.rf_model_original, feature_perturbation = 'interventional')
        #     shap_values = explainer(sample_X)
        # local_importance = np.abs(shap_values.values)[:,:, 0]
        # global_importance = local_importance.mean(axis=0)
        # self.feature_value_dict['treeshap'] = global_importance
        # self.df_value_dict['treeshap'] = local_importance
        # self.time_dict['treeshap']=time()-time_init
        # print("Done: TreeSHAP computation")
        # 2d-SHAP
        
        print("Start: 2d-SHAP computation")

        time_init=time()
        knn_2d_values = knn_2d.knnsv2d(self.X, self.y, self.X_val, self.y_val).T
        self.data_value_dict['2d-knn'] = knn_2d_values.mean(axis=1)
        self.feature_value_dict['2d-knn'] = knn_2d_values.mean(axis=0)
        self.df_value_dict['2d-knn'] = knn_2d_values
        self.time_dict['2d-knn']=time()-time_init

        
        # time_init=time()
        # mc_2d_values = mc_2d.mcsv2d(self.X, self.y, self.X_val, self.y_val)
        # self.data_value_dict['2d-mc'] = mc_2d_values.mean(axis=1)
        # self.feature_value_dict['2d-mc'] = mc_2d_values.mean(axis=0)
        # self.df_value_dict['2d-mc'] = mc_2d_values
        # self.time_dict['2d-mc']=time()-time_init

        print("Done: 2d-SHAP computation")

    def evaluate_data_values(self, noisy_index, beta_true, error_index, error_row_index, X_test, y_test,
                             experiments, outlier_inds=None):# outlier_inds_0=None, outlier_inds_1=None):

        
        if 'noisy' in experiments:
            time_init=time()
            self.noisy_detect_dict=utils_eval.noisy_detection_experiment(self.data_value_dict, noisy_index)
            self.time_dict['Eval:noisy']=time()-time_init
            
        if 'point_removal' in experiments:
            sampling = False
            time_init=time()
            if sampling:
                noisy_rate = len(noisy_index)/self.X.shape[0]
                idx_sub = np.sort(np.concatenate((np.random.choice(noisy_index,int(200*noisy_rate),replace=False),
                    np.random.choice(np.setdiff1d(np.arange(self.X.shape[0]),noisy_index),
                                    int(200*(1-noisy_rate)),replace=False))))
                X_sub = self.X[idx_sub]
                y_sub = self.y[idx_sub]
                data_value_dict_sub = {}
                for key,value in self.data_value_dict.items():
                    data_value_dict_sub[key] = value[idx_sub]
                self.point_removal_dict=utils_eval.point_removal_experiment(data_value_dict_sub,
                                                                        X_sub, y_sub,
                                                                        self.X_test, self.y_test,
                                                                        problem=self.problem)
            else:
                self.point_removal_dict=utils_eval.point_removal_experiment(self.data_value_dict,
                                                        self.X, self.y,
                                                        self.X_test, self.y_test,
                                                        problem=self.problem)
            self.time_dict['Eval:removal']=time()-time_init

        if 'feature_removal' in experiments:
            time_init=time()
            self.feature_removal_dict=utils_eval.feature_removal_experiment(self.feature_value_dict, self.X, self.y, self.X_test, self.y_test)
            self.time_dict['Eval:feature_removal']=time()-time_init
            
        if 'cell_removal' in experiments:
            time_init=time()
            self.cell_removal_dict=utils_eval.cell_removal_experiment(self.df_value_dict, self.X, self.y, self.X_test, self.y_test)
            self.time_dict['Eval:cell_removal']=time()-time_init
        
        if 'outlier' in experiments:
            time_init=time()
            self.outlier_detect_dict=utils_eval.outlier_detection_experiment(self.df_value_dict, outlier_inds,self.X, self.y)
            # self.outlier_detect_dict=utils_eval.outlier_detection_experiment(self.df_value_dict, outlier_inds_0, outlier_inds_1,self.X, self.y)
            self.time_dict['Eval:outlier']=time()-time_init

        if 'error' in experiments:
            time_init=time()
            self.error_detect_dict=utils_eval.error_detection_experiment(self.df_value_dict, error_index, error_row_index,
                                                                         two_stage = False, data_value_dict = self.data_value_dict)
            self.time_dict['Eval:error']=time()-time_init
        

    def save_results(self, runpath, dataset, dargs_ind, noisy_index, beta_true,
                     error_index=None,error_row_index=None):

        print('-'*50)
        print('Save results')
        print('-'*50)
        result_dict={
            # 'data': {"X":self.X,"y":self.y,"X_val":self.X_val,"y_val":self.y_val,"X_test":self.X_test,"y_test":self.y_test},
                    'data_value': self.data_value_dict,
                     'feature_value': self.feature_value_dict,
                     'df_value': self.df_value_dict,
                     'time': self.time_dict,
                     'noisy': self.noisy_detect_dict,
                     'mask': self.mask_detect_dict,
                     "rank":self.rank_dict,
                     'error':self.error_detect_dict,
                     'outlier':self.outlier_detect_dict,
                     'point_removal': self.point_removal_dict,
                     'feature_removal':self.feature_removal_dict,
                     'cell_removal':self.cell_removal_dict,
                     'loo':self.loo_dict,
                     'dargs':self.dargs,
                     'dataset':dataset,
                     'input_dim':self.X.shape[1],
                     'model_name':self.model_name,
                     'noisy_index': noisy_index,
                     'beta_true': beta_true,
                     'error_row_index':error_row_index,
                     'error_index':error_index
                     }
        with open(runpath+f'/run_id{self.run_id}_{dargs_ind}.pkl', 'wb') as handle:
            pickle.dump(result_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
        print(f'Done! path: {runpath}, run_id: {self.run_id}.',flush=True)











