#!/usr/bin/env python
# coding: utf-8

# 
# # data issue : The threshold score for Model3 should be 20 rather than 30. 
# 
# Setting is as 30 will make it never get hit.
# 
# 
# As I don't have database on my PC and my company forbids user personal data on company database.  
# I will use python and provide a pseudo sql code. As SQL is very easy.
# 
# 

# In[1]:


import pandas as pd
import numpy as np
from pandas.tseries.offsets import MonthEnd


# # 1. Seperate three tables into Model_table, Rule_table and Hit table

# In[2]:


model_table = pd.read_csv('Model_table.csv') # after typo fixed
rule_table = pd.read_csv('Rule_table.csv') 
hit_table = pd.read_csv('Hit_table.csv')


# In[6]:


model_table.head(1)


# In[7]:


rule_table.head(1)


# In[8]:


hit_table.head(1)


# In[9]:


# change model name from Mod1 to Mod1_INV or Mod1_CP, to join with other table directly
rule_table['Model_name'] = rule_table['Model name'] + "_" + np.where(rule_table['Customer type'] == 'Individual','INV','CP')

# get corresponding Sunday, for agg
hit_table['Hit_Date'] = pd.to_datetime(hit_table['Hit_Date'])
hit_table['week_sunday'] = hit_table['Hit_Date'].apply(lambda d: d + pd.Timedelta(days=(6-d.weekday())))

# dedpup: only the first hit contributes to the total score within 7 days
hit_table['multi_hit_same_rule'] = hit_table.groupby(['Rule_name', 'Customer_ID', 'week_sunday'])['Hit_Date'].rank(method='first').astype(int)
hit_table_dedup = hit_table.loc[hit_table['multi_hit_same_rule'] == 1]

# after dedup, join with rule_table to calculate the alter score
hit_dedup_score = hit_table_dedup.merge(rule_table, left_on=['Rule_name', 'Customer_type'], right_on=['Rule name', 'Customer type'], how='left')


# cal score for each customer on each model within each 7 days
hit_score_agg = hit_dedup_score.groupby(['Customer_ID','Customer_type', 'Model_name', 'week_sunday'])['Score'].sum()

# merge with Model table to get the threshold 
hit_score_agg2 = hit_score_agg.reset_index().merge(model_table, left_on=['Model_name'], right_on=['Model_name'], how='left')

# filter cum score equal or exceed model threshold
hit_alerts = hit_score_agg2.loc[hit_score_agg2['Score'] >= hit_score_agg2['Threshold']]


# get month end for agg
hit_alerts['mth_end'] = hit_alerts['week_sunday'] + MonthEnd(0)

# get the monthly alter trends overview
hit_alerts_agg = hit_alerts.groupby(['Model_name','mth_end'])[hit_alerts.columns[0]].count().reset_index()
hit_alerts_agg.pivot(index='Model_name', columns='mth_end', values='Customer_ID').fillna(0)


# ## Get Rule hits Overview

# In[10]:


hit_count = hit_table.groupby('Rule_name')['Customer_ID'].count().reset_index()
hit_count.rename(columns={'Customer_ID':'Number of Hits'})


# ### For Number of Alter, one rule can trigger alter on multi models

# In[13]:


hit_trend = hit_alerts[['Customer_ID', 'Model_name', 'week_sunday']].merge(hit_dedup_score, how='left', on=['Customer_ID', 'Model_name', 'week_sunday'])


# In[15]:


hit_alter_trend = hit_trend.groupby('Rule_name')['Customer_ID'].count().reset_index()
hit_alter_trend.rename(columns={'Customer_ID':'Number of Alters'})


# ### General statistics

# In[16]:


alerts_by_customer = hit_alerts.groupby('Customer_ID')['Model_name'].count().reset_index().sort_values('Model_name', ascending=False)
alerts_by_customer.rename(columns={'Model_name':'Number of alerts'}).iloc[0,:]


# In[17]:


alerts_by_type = hit_alerts.groupby('Customer_type')['Model_name'].count().reset_index()
alerts_by_type.rename(columns={'Model_name':'Number of alerts'})


# In[ ]:





# # Appendix code

# ### upload large data to database
# 
# Using Snowflake as an example

# In[ ]:


user = 'XXX'
pwd='XXX'

import sys
import os


import pandas as pd
import snowflake.connector
import os 
#import userpwd
def get_df(qy):
    con = snowflake.connector.connect(
    user=user,
    password=pwd,
    authenticator="https://didentity.okta.com",
    role='ROLE_' + str(user),
    account="yourcomapny.web.link"
    )
    cursor = con.cursor()
    cursor.execute('USE warehouse warehousewarehouse1_YOUR')
    cursor.execute('USE database DDPROD_YOUR')
    cursor.execute('USE schema WS_YOUR')
    query = qy
    results = cursor.execute(query)
    outdata = pd.DataFrame.from_records(iter(results), columns=[x[0] for x in results.description])
    print(outdata.shape)
    cursor.close()
    con.close()
    return(outdata)

def push_df(df,date_columns,table_name):
    con = snowflake.connector.connect(
    user=user,
    password=pwd,
    authenticator="https://didentity.okta.com",
    role='ROLE_' + str(user),
    account="dfs.us-east-1.privatelink"
    )
    cursor = con.cursor()
    cursor.execute('USE warehouse warehousewarehouse1_YOUR')
    cursor.execute('USE database DDPROD_YOUR')
    cursor.execute('USE schema WS_YOUR')
    
    n_cols_csv = df.shape[1]
    n_rows_csv = df.shape[0]
    

    # Only consider datetime column 

    table_type = []
    for item in df.columns.values:
        if (df[item].dtypes == object) or (df[item].dtypes=='<M8[ns]'):
            if item not in date_columns:
                table_col_type = 'varchar'
            else:
                table_col_type = 'date'
        else:
            if isinstance(df.reset_index(drop=True).loc[0,item],int):
                table_col_type = 'integer'
            else:
                table_col_type = 'float'
        table_type.append(item +' '+ table_col_type)
    table_string = ','.join(table_type)
    df.to_csv('TMP.csv.gz', compression='gzip', index = False, sep = ',')
  
    create_table_query = f'''CREATE OR REPLACE TABLE {table_name}({table_string})'''
    cursor.execute(create_table_query)
    csv_file_path='TMP.csv.gz'
    cursor.execute( 'remove @~/TMP.csv.gz')
    cursor.execute(f'''put file://{csv_file_path}* @%{table_name}''')
    cursor.execute(f'''copy into "DB"."SCHEMA"."{table_name}"  file_format = (TYPE=CSV FIELD_DELIMITER = ","  SKIP_HEADER = 1 )''')
    
    os.remove('TMP.csv.gz')
    cursor.close()
    con.close()
   

