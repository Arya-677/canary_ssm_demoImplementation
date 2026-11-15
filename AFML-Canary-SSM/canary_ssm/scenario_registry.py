"""Role and pair registration shared by two explicitly different generators."""
from dataclasses import asdict,dataclass
import hashlib
import json
from .seeds import seed_for,purpose_span,REGISTRY_VERSION

ADDITIVE_GENERATOR_ID='statistical-additive-latency-v1'
WORLD_GENERATOR_ID='resource-world-scenarios-v1'
ROLES={'smoke':'smoke','development':'dev','threshold-calibration':'calibration',
       'null-validation':'null_validation','final-test':'test'}
WORLD_FAMILIES=('healthy','host_fault','rack_fault','shared_demand_surge',
                'transient_degradation','persistent_degradation','recovery')
ADDITIVE_FAMILIES=('additive_baseline','additive_transient','additive_persistent','additive_recovery')
GENERATORS={WORLD_GENERATOR_ID:WORLD_FAMILIES,ADDITIVE_GENERATOR_ID:ADDITIVE_FAMILIES}
USES={'smoke':('debug',),'development':('fit','tune'),
      'threshold-calibration':('threshold',),'null-validation':('audit',),'final-test':('evaluate',)}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class PairSpec:
    generator_id:str
    role:str
    family:str
    index:int
    seed:int
    seed_purpose:str
    family_index:int
    pair_id:str
    members:tuple[str,...]=('null','harm')

    def to_dict(self):
        row=asdict(self);row['members']=list(self.members);return row

    @classmethod
    def from_dict(cls,row):
        if not isinstance(row,dict):raise ValueError('Pair metadata must be an object')
        row=dict(row)
        try:
            if 'members' in row:row['members']=tuple(row['members'])
            return cls(**row).validate()
        except (TypeError,KeyError) as exc:raise ValueError('Invalid pair metadata') from exc

    @classmethod
    def register(cls,generator_id,role,family,index=0):
        if generator_id not in GENERATORS or role not in ROLES or family not in GENERATORS[generator_id]:
            raise ValueError('Unknown generator, role or scenario family')
        if type(index) is not int or not 0<=index<20000:raise ValueError('Invalid pair index')
        purpose=('world_' if generator_id==WORLD_GENERATOR_ID else 'additive_')+ROLES[role]
        family_index=GENERATORS[generator_id].index(family)
        seed=seed_for(purpose,index,family_index)
        key={'generator_id':generator_id,'role':role,'family':family,'index':index,'seed':seed}
        return cls(generator_id,role,family,index,seed,purpose,family_index,digest(key)[:24])

    def validate(self):
        expected=self.register(self.generator_id,self.role,self.family,self.index)
        if self!=expected:raise ValueError('Pair registration changed, split or moved between roles')
        return self

    def run_id(self,member):
        self.validate()
        if member not in self.members:raise ValueError('Unknown pair member')
        # Public identities must not reveal role, scenario kind or null/harm labels.
        return 'run-'+digest([self.generator_id,self.pair_id,member])[:32]


def register_bundles(pairs_per_family=1):
    if type(pairs_per_family) is not int or not 1<=pairs_per_family<=3:
        raise ValueError('Tiny registry supports 1–3 pairs per family')
    pairs=[PairSpec.register(g,role,f,i) for g,families in GENERATORS.items()
           for role in ROLES for f in families for i in range(pairs_per_family)]
    validate_registry(pairs)
    return pairs


def validate_registry(pairs):
    seeds={};ids=set();runs=set()
    for pair in pairs:
        pair.validate()
        if pair.pair_id in ids or pair.seed in seeds:raise ValueError('Duplicate pair or seed across bundles')
        ids.add(pair.pair_id);seeds[pair.seed]=pair.pair_id
        for member in pair.members:
            run=pair.run_id(member)
            if run in runs:raise ValueError('Duplicate scenario member ID')
            runs.add(run)
    return True


def registry_manifest(pairs_per_family=1):
    pairs=register_bundles(pairs_per_family)
    rows=[p.to_dict()|{'scenario_ids':{m:p.run_id(m) for m in p.members}} for p in pairs]
    value={'registry_id':'scenario-bundles-v1','seed_registry_version':REGISTRY_VERSION,
        'roles':{role:{'allowed_uses':list(USES[role]),'null_only':role in ('threshold-calibration','null-validation'),
            'materialized_by_default':role=='smoke'} for role in ROLES},
        'generator_ids':list(GENERATORS),'pairs':rows,
        'world_seed_spans':{role:list(purpose_span('world_'+purpose)) for role,purpose in ROLES.items()},
        'additive_seed_spans':{role:list(purpose_span('additive_'+purpose)) for role,purpose in ROLES.items()}}
    return value|{'registry_sha256':digest(value)}


def select_members(pairs,role,use,member=None):
    if role not in USES or use not in USES[role]:raise ValueError('Role is not permitted for this data use')
    validate_registry(pairs)
    selected=[]
    for pair in pairs:
        if pair.role!=role:continue
        members=('null',) if role in ('threshold-calibration','null-validation') else pair.members
        if member is not None:
            if member not in members:raise ValueError('Requested member is not eligible for this role/use')
            members=(member,)
        selected.extend({'pair_id':pair.pair_id,'role':role,'member':m,'scenario_id':pair.run_id(m)} for m in members)
    return selected
