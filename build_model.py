#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
The code does the following:
     Load in the raw data (opendata_projects.csv and donations_counts.csv)
     Compute featurized dataset from the raw data
     Build random-forest model (using the finalized model that is chosen)
        NOTE: The model should be finalized first. This file will only take in the finalized model.
     Save the model
     Save some diagnostics about the model (we have yet to do this)
'''

##

'''
NOTE: If we want to pass arguments from the command line, we can do that using setup of code below.
I'm not sure what arguments we would need to pass along to this particular file.
Maybe the file names?

import argparse
import sys

args=sys.argv[1:]
print(args[0])
print(args[1])
'''

# # ------------------------------------------------ # # 
# # STEP 1 and 2: Load in raw data, create features: # #
# # ------------------------------------------------ # #


'''
NOTE:
     The code here is all from donors-choose-data-prep.py.
     It does not include splitting into train-test, or writing out of CSV files.
     If we change the donors-choose-data-prep.py, we will have to change here as well!!
'''


from __future__ import division
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pylab
import re
import string
from operator import itemgetter
from pandas import *


# Global variables
state_rank_count = 50

# Read in opendata_projects file and donation_counts project file
projects = pd.read_csv('../Data/opendata_projects.csv', index_col = False)

donations = pd.read_csv('../Data/donations_counts.csv')

# Use "shipping cost" variable to created binary variable indicating whether a project has free shipping
shipping = pd.DataFrame(projects['vendor_shipping_charges'])
# if shipping_charges = 0 , t
# if shipping_charges > 0 , f
shipping[shipping == 0] = -1
shipping[shipping > 0] = 'No'
shipping[shipping == -1] = 'Yes'

shipping.columns.values[0]='free_shipping'

# Function to count the number of days between start_date and complete_date
from dateutil.parser import parse
import math
import time

def day_count(date0, date1):
    if isinstance(date0, float) or isinstance(date1, float):
        return 'NaN'
    try:
        delta = parse(date0) - parse(date1)
        delta = delta.days
        if delta < 0:
            delta = 'NaN'       
        elif delta == 0:
            delta = 1      
        else:
            delta = delta
    except Exception, e:
        print date1, type(date1), date0, type(date0)
        raise e
    return delta

# Apply dayCount function over dataframe
def date_calc(row):
    return day_count(row['date_completed'], row['date_posted'])
date_diff = projects.apply(date_calc, 1)

# Create single vector dataframe of days to completion
days_to_comp = pd.DataFrame({'days_to_completion': pd.Series(date_diff)})

# Subset opendata_projects to include only live projects
live_projects = projects[projects.funding_status == 'live']

# Add column of current date so we can count open days
live_projects['current_date'] = '2014-11-10'

# Apply dayCount over live projects
def date_calc2(row):
    return day_count(row['current_date'], row['date_posted'])
date_diff2 = live_projects.apply(date_calc2, 1)

# Create single vector dataframe of days open. If project live fewer than 30 days, set days live to NA
days_live = pd.DataFrame({'days_open': pd.Series(date_diff2)})

# Add the dataframes containing days_to_completion and days_open to projects dataframe
projects = pd.concat([projects, days_to_comp, days_live, shipping], axis = 1)

# Consider all reallocated projects and all projects live for more than 30 days as not funded at all. Delete all remaining live projects (which have been live for less than 30 days)
projects.ix[projects.days_to_completion <= 30, 'funded_by_30'] = 'Yes'
projects.ix[projects.days_to_completion > 30, 'funded_by_30'] = 'No'
projects.ix[projects.funding_status=='reallocated', 'funded_by_30'] = 'No'
projects.ix[projects.days_open > 30, 'funded_by_30'] = 'No'

projects = projects[projects.funded_by_30.notnull()]

# Create donor interest parameters by subject and poverty level

# By SUBJECT
# Deal with missing values
index = np.where(projects['primary_focus_subject'].isnull())[0]
projects.loc[index, 'primary_focus_subject'] = 'Missing'
total_size = len(projects) 
total_donors = projects['num_donors'].sum()

subjects = projects['primary_focus_subject']
subjects = subjects.unique()
subjects.sort()

num_donors_sub = projects.groupby(['primary_focus_subject']).sum()['num_donors']
subjects_size = projects.groupby('primary_focus_subject').size()
subjects_prop = subjects_size / total_size
scaled_interest_par_sub = (num_donors_sub/total_donors)**2 /subjects_prop 

df = pd.DataFrame({'primary_focus_subject': subjects, 'scaled_interest_par_sub' : scaled_interest_par_sub.values})
projects = pd.merge(projects, df, left_on = 'primary_focus_subject', right_on='primary_focus_subject', how='left')

# By POVERTY LEVEL
# Deal with missing values
index = np.where(projects['poverty_level'].isnull())[0]
projects.loc[index, 'poverty_level'] = 'Missing'
total_size = len(projects) 
total_donors = projects['num_donors'].sum()

poverty = projects['poverty_level']
poverty = poverty.unique()
poverty.sort()

num_donors_pov = projects.groupby(['poverty_level']).sum()['num_donors']
poverty_size = projects.groupby('poverty_level').size()
poverty_prop = poverty_size / total_size
scaled_interest_par_pov = (num_donors_pov/total_donors)**2 /poverty_prop

df = pd.DataFrame({'poverty_level': poverty, 'scaled_interest_par_pov' : scaled_interest_par_pov.values})
projects = pd.merge(projects, df, left_on = 'poverty_level', right_on='poverty_level', how='left')

#projects.columns

#Replace missing values as NaN
projects = projects.replace('Missing', np.nan)

# Combine city, state into city_state variable in projects dataframe
projects['city_state'] = projects['school_city'] + ', ' + projects['school_state']

# Get the count of the completed projects from each city_state
# and create levels from the top 50, and group all remaining into 51st category
comp = projects[projects.funding_status == 'completed']
counts = comp['city_state'].value_counts()
ranks = pd.DataFrame([x+1 for x in range(counts.shape[0])], columns = ['completion_rank'])
names = pd.DataFrame(counts.index, columns = ['city_state'])

ranks = pd.concat([names, ranks], axis = 1)
ranks['city_state_cat'] = ranks['city_state']

ranks['city_state_cat'][ranks.completion_rank > state_rank_count] = 'Other'

# Join the ranks table and projects table on the city_state columns
projects = projects.merge(ranks, how = 'right', on = 'city_state')

# Join the donations table and projects table on the city_state column
projects = projects.merge(donations, how = 'right', on = 'city_state')

# Read in outside data
outside_dat =  pd.read_csv('../Data/outside_dat.csv', dtype = {'zip': np.str_, 'med_inc': np.float64, 'pop': np.float64, 'party': np.str_})

# Merge outside_data with projects
projects = projects.merge(outside_dat, on = 'school_zip', how='left')

# Drop last 20986 rows because those rows only have outside data
projects = projects.drop(projects.tail(20986).index)

# WE NOW HAVE FINALIZED THE DATA


# # ------------------------------------------------ # # 
# #           STEP 3: CREATE THE MODEL               # #
# # ------------------------------------------------ # #

# code here needs work:
m = model.learn(df, ANY OTHER ARGS?)
# ?
# projects.m() # not sure how this works yet

# # ---------------------------------------------- # # 
# #     STEP 4 & 5: SAVE MODEL + DIAGNOSTICS       # #
# # ---------------------------------------------- # #

# save model:
# msave("model.rf") # ?
# save diagnostics about the model


# In command line, type: python build_model.py
 





