#! /home/umisora675/tools/anaconda3/bin/python

import sys
import os
import yaml
import sqlite3
import argparse
import pandas as pd
import subprocess as sp
from datetime import datetime as dt
from datetime import timedelta as td
import plotly.graph_objects as go
import plotly.offline as po
import plotly.express as px


#   ____________________________________________________________
#__/ [*] Argument Parse                                         \_______
#
parser          =   argparse.ArgumentParser()
parser.add_argument('-y', '--yaml', help='Specify configuration yaml file', required=True)
parser.add_argument('-s', '--sql', help='Specify SQLite3 db or PostgreSQL url', required=True)
args = parser.parse_args()



#   ____________________________________________________________
#__/ [*] Read configure                                         \_______
#
config = None
with open(args.yaml, 'r') as yml:
    config = yaml.load(yml, Loader=yaml.CLoader)


#   ____________________________________________________________
#__/ [*] Check dir size                                         \_______
#
now =   dt.now()
dfs =   dict()
for d in config["directory"]:
    ## Check directory exists or not.
    if os.path.isdir(d["path"]):
        print(f"**KIC-Info : check {d['path']} directory",file=sys.stderr )
    else:
        print(f"**KIC-ERROR!! : There is no {d['path']} directory!",file=sys.stderr )
        continue

    res =   None
    df  =   pd.DataFrame(columns=["date","dir","size_byte","last_update"])
    try:
        depth = d["depth"] if "depth" in d else 1
        res     =   sp.run(['du', '--all' , '--time' , '--max-depth' , str(depth) , d["path"]], encoding='utf-8', stdout=sp.PIPE, stderr=sp.PIPE)

    except sp.CalledProcessError as e:
        print('ERROR:', e.output)

    for i in [l.split("\t") for l in res.stdout.split("\n")]:
        ## skip blank responce
        if len(i) == 1:
            continue

        ## remove d["path"] string from dir
        dir =   i[2].replace(f'{d["path"]}/','')
        df  =   df.append({"date" : now, "size_byte" : i[0], "dir" : dir, "last_update" : dt.strptime(i[1],'%Y-%m-%d %H:%M')},ignore_index=True)

    ## confirm sql, sqlite3 or Postgre
    conn = None
    if "http" in args.sql:
        pass
    else:
        conn = sqlite3.connect(args.sql)

    ## export to sql
    df.to_sql(d["path"],conn,if_exists='append',index=None)
    conn.close()

    dfs[d["path"]]  =   df


#   ____________________________________________________________
#__/ [*] Create graph                                           \_______
#

for n,d in dfs.items():
    ## inisialize alert setting
    status_alert    =   False
    check_older     =   None

    ## change size to GA
    d = d.astype({'size_byte': 'float'})
    d["size"] = d["size_byte"] / 1024**2

    ## pickup top dir data
    se_top  =   d[d["dir"] == n]
    ## rempve top dir data
    d       =   d[d["dir"] != n]

    ## check alert value.
    for c in config["directory"]:
        if c["path"] != n:
            continue

        if "alert" in c and "value" in c["alert"]:
            if float(se_top["size"].values[0]) > float(c["alert"]["value"]):
                status_alert    =   True

        if "older" in c:
            check_older = c["older"]


    #   ____________________________________________________________
    #__/ [*] Prepare DataFrame for plotly                           \_______
    #
    ## add parent info
    get_parent = lambda x: n if len(x.split("/")) == 1 else x.split("/")[-2]
    d["parents"]        =   d["dir"].map(get_parent)
    se_top["parents"]   =   ""

    ## merge d and se_top
    d = d.append(se_top,ignore_index=True)


    #   ____________________________________________________________
    #__/ [*] Create graph When alert true                           \_______
    #
    if status_alert:
        labels = d["dir"].to_list()
        values = d["size"].to_list()
        parents = d["parents"].to_list()


        ## create dir size check graph
        fig = go.Figure(go.Sunburst(labels=labels,parents=parents,values=values,branchvalues="total"))
        fig.update_layout(margin = dict(t=0, l=0, r=0, b=0),
                        title={"text" : f"{n} directory usage" , 'y':0.9, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'})
        n = n.replace("/","_")
        po.plot(fig, filename=f"{n}.html", auto_open=False)


    #   ____________________________________________________________
    #__/ [*] Create graph When older active                         \_______
    #
    if check_older is not None:
        d = d.sort_values("last_update",ascending=True).reset_index()
        d = d[d["last_update"] < now - td(days=int(check_older))]


        ## create graph
        d["last_update"] = d["last_update"].dt.strftime('%Y/%m/%d %H:%M')
        fig2 = px.bar(d,x="dir",y="size",hover_data=["last_update"])
        fig2.update_layout(title={"text": f"{n} older than {check_older} days",'y':0.9, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'})
        po.plot(fig2, filename=f"{n}_older.html", auto_open=False)
        #fig2.to_image("png",engine="kaleido")
        #fig2.write_image(f"{n}_older.png")

