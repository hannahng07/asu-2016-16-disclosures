import pandas as pd, os, json
BASE=os.path.join(os.path.expanduser('~'),'mnt','Grant and Nguyen')
idx=pd.read_csv(os.path.join(BASE,'dta_probe','reader_packet_index_Claude.csv'))
vd=os.path.join(BASE,'reader_verdicts')
done={f[:-5] for f in os.listdir(vd) if f.endswith('.json')}
idx['stem']=idx.file.str.replace('.txt','',regex=False)
todo=idx[~idx.stem.isin(done)].sort_values('tick')
print(f"packets {len(idx)}  done {len(done)}  TODO {len(todo)}")
print(json.dumps(todo.stem.tolist()))
