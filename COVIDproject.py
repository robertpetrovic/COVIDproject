#pip install plotly

import plotly.io as pio
pio.renderers.default='browser'

from urllib.request import urlopen
import json
import pandas as pd
pd.options.mode.chained_assignment = None
print('\nThis program pulls live data from every county in Texas to calculate how likely an event, like a party or wedding, will have at least one person with COVID-19.')
print('Once the data is loaded, enter the number of people at the event, as well as the number of days to postpone the event to see how the probability changes.')
print('Loading data from sources...')

#geometry information for all US - not Texas - counties
with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
    counties = json.load(response)

#NYTimes takes data from officials sources like Texas DSHS but also accounts for corroborating evidence from journalists
#to combat alleged underreporting of cases
#data is cumulative cases per county of all US - not just Texas
case_track = pd.read_csv('https://raw.githubusercontent.com/nytimes/covid-19-data/master/us-counties.csv',
                        usecols=['date','county','state','fips','cases'])
case_track = case_track[case_track['state']=='Texas']
case_track['date'] = pd.to_datetime(case_track['date'])

#14 days is a commonly used duration in the scientific consensus on when a case is most likely to be contagious
from datetime import timedelta
new = case_track['date'].max()
old = new - timedelta(14)
case_track = case_track[(case_track['date']==new)|(case_track['date']==old)]

#case data has been reduced to the net number of cases over the last 14 days
old_df = case_track.iloc[:251]
new_df = case_track.iloc[251:]
merged = old_df.merge(new_df,how='left',on=['fips','county','state'],suffixes=['_old','_new'])
merged['14_day_change'] = merged['cases_new'] - merged['cases_old']
merged['fips'] = merged['fips'].astype(int)

df = merged[['county','fips','14_day_change']]
df.columns = ['County','FIPS_code','Cases in Last 2 Weeks']
#net negative cases are set to 0 cases for simplicity's sake in assuming how many are infectious in a county
df.loc[df['Cases in Last 2 Weeks']<0, 'Cases in Last 2 Weeks'] = 0

#county population data from US Census
#filtered for only Texas counties, then cleaned the county name strings to match df (covid case) county naming
populations = pd.read_excel('https://www2.census.gov/programs-surveys/popest/tables/2010-2019/counties/totals/co-est2019-annres.xlsx',
                            skiprows=4,skipfooter=6,usecols=[0,12],names=['County','Population'])
populations = populations[populations['County'].str.contains(', Texas',regex=False)]
county_names = populations['County']
county_names = [x.strip('.') for x in county_names]
county_names = [x.split(' County')[0] for x in county_names]
populations['County'] = county_names

df = df.merge(populations,on='County',how='left')
df['2 Weeks Cases per 100,000'] = (100000*df.loc[:,'Cases in Last 2 Weeks']/df.loc[:,'Population']).astype(int)

#county rt values calculated by Xihong Lin Lab Group at Harvard
rt_reader = pd.read_csv('https://github.com/lin-lab/COVID19-Viz/raw/master/clean_data/rt_table_export.csv.zip',
                       chunksize=10000,parse_dates=['date'])

county_rts = pd.DataFrame()

for chunk in rt_reader:
    #filters for Texas counties
    all_data = chunk[(chunk['UID']>=84048001)&(chunk['UID']<=84048507)]
    relevant_data = all_data[['UID','date','Rt_loess_fit']]
    county_rts = county_rts.append(relevant_data)

#reduces dataframe to only the most up-to-date values
county_rts = county_rts[county_rts.date==county_rts.date.max()]
county_rts = county_rts.drop('date',axis=1)

#it is mathematically difficult to calculate rt values in small populations, so these values are set to NaN by Lin Lab Group
#here a value of 1.0 is used as a placeholder
county_rts = county_rts.fillna(value=1.0)
#stripped the US UID prefix 840 to match with population dataframe
county_rts['UID'] = county_rts['UID']-84000000
county_rts.columns = ['FIPS_code','rt']
df = df.merge(county_rts,on='FIPS_code',how='left')

import math

#projects how many cases there will be in a given amount of days
def projection(row,people,days):
    current = row['Cases in Last 2 Weeks']
    rt = round(row['rt'],5)
    
    #formula was derived manually from a series of time spans where the nationwide reproductive value (Rt) was 
    #constant, case numbers as a function of time were used to generate exponential growth equations, then a line of 
    #best fit was generated comparing Rt values to the functions' exponents
    if (days>=30)&(current * round(math.exp((rt-1)*0.222*30)) > row['Population']):
        #an exponential model is used, so the hypothetical case number ceiling is set to the county's population
        cases = row['Population']
    else:
        cases = current * round(math.exp((rt-1)*0.222*days))
        
    if cases>row['Population']: cases = row['Population']
    
    #returns probabilty of there being at least one COVID carrier attending an event of a given number of people
    per_capita = round(cases/row['Population'],5)
    return str(int(100*(1-round((1-per_capita)**people,5))))+'%'


import plotly.express as px

#generates, for every county, the probability of there being at least one COVID carrier attending an event with
#a user-inputted number of people, and the new probability if the event were postponed a user-inputted number of days
#these probabilities are presented as an interactive map, counties are color coded by cases per 100,000

def generate(people,days):
    people = int(people)
    days = int(days)
    df['At Least 1 Carrier Probability'] = df.apply(lambda row: projection(row,people,0), axis=1)
    df['Likely Prob. After Waiting'] = df.apply(lambda row: projection(row,people,days), axis=1)
    
    cases = '2 Weeks Cases per 100,000'
    fig = px.choropleth_mapbox(df, geojson=counties, locations='FIPS_code', hover_name='County',
                           hover_data={cases:True,'FIPS_code':False,'At Least 1 Carrier Probability':True,
                                      'Likely Prob. After Waiting':True},color=cases,
                           color_continuous_scale="Reds",
                           #color scale maximum is set to mean + 2 standard deviations rather than max to prevent
                           #outliers from dwarfing the majority of the data:
                           range_color=(0, round(df[cases].mean()+2*df[cases].std(),-2)),
                           mapbox_style="carto-positron",
                           zoom=5, center = {"lat": 31.1322, "lon": -99.3413}, 
                           opacity=0.7
                          )
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    fig.show()


while True:
    try:
        people = input('How many people will be at the event?')
        days = input('How many days would you like to postpone the event?')
        generate(people,days)
        break
    except:
        print('\nYou must enter two positive integers\n')
