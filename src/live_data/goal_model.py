"""Regularized attack/defence Poisson; date-weighted likelihood and optional DC.

Only pre-cutoff results enter fit. Domestic and European games share club
parameters; competitions have their own intercept and home advantage.
"""
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln
from scipy.stats import poisson
from data_store import before

MODEL_VERSION='attack-defence-v2'

@dataclass(frozen=True)
class ModelConfig:
    half_life_days: float=365.
    regularization: float=10.
    dixon_coles: bool=True

def score_distribution(lam_h,lam_a,rho=0.):
    if not np.isfinite([lam_h,lam_a,rho]).all() or min(lam_h,lam_a)<=0:
        raise ValueError('Invalid goal intensities')
    # Adapt support to retain all but <1e-12 of each tail. No 8+ bucket masquerading as 8.
    n=max(12,int(poisson.ppf(1-1e-12,max(lam_h,lam_a))))
    matrix=np.outer(poisson.pmf(np.arange(n+1),lam_h),poisson.pmf(np.arange(n+1),lam_a))
    lower=max(-1/lam_h,-1/lam_a)+1e-10
    upper=min(1.,1/(lam_h*lam_a))-1e-10
    rho=float(np.clip(rho,lower,upper))
    matrix[0,0]*=1-lam_h*lam_a*rho
    matrix[0,1]*=1+lam_h*rho
    matrix[1,0]*=1+lam_a*rho
    matrix[1,1]*=1-rho
    matrix/=matrix.sum()
    return matrix

def market_summary(lam_h,lam_a,rho=0.,lines=(.5,1.5,2.5,3.5)):
    m=score_distribution(lam_h,lam_a,rho)
    p=np.array([np.tril(m,-1).sum(),np.trace(m),np.triu(m,1).sum()])
    scores=np.dstack(np.unravel_index(np.argsort(m.ravel())[::-1][:5],m.shape))[0]
    total=np.add.outer(np.arange(m.shape[0]),np.arange(m.shape[1]))
    return {'p_home_win':float(p[0]),'p_draw':float(p[1]),'p_away_win':float(p[2]),
            'marcadores_top5':[(f'{h}-{a}',round(float(m[h,a])*100,2)) for h,a in scores],
            'btts':float(m[1:,1:].sum()),
            'goal_lines':{str(line):{'over':float(m[total>line].sum()),'under':float(m[total<line].sum()),'push':float(m[total==line].sum())} for line in lines}}

class AttackDefenceModel:
    def __init__(self,config=None):self.config=config or ModelConfig()

    def fit(self,results,cutoff):
        df=before(results,cutoff).dropna(subset=['home_team','away_team','home_score','away_score']).sort_values(['date','match_id'])
        if len(df)<30:raise ValueError('Need at least 30 dated matches')
        self.cutoff=pd.Timestamp(cutoff).normalize();self.latest=df.date.max();self.n_matches=len(df)
        self.teams={x:i for i,x in enumerate(sorted(set(df.home_team)|set(df.away_team)))}
        self.competitions={x:i for i,x in enumerate(sorted(df.tournament.unique()))}
        n=len(self.teams);k=len(self.competitions)
        h=df.home_team.map(self.teams).to_numpy();a=df.away_team.map(self.teams).to_numpy();c=df.tournament.map(self.competitions).to_numpy()
        yh=df.home_score.to_numpy(float);ya=df.away_score.to_numpy(float)
        neutral=df.get('neutral',pd.Series(False,index=df.index)).to_numpy(bool);home_flag=(~neutral).astype(float)
        weights=np.exp(-np.log(2)*(self.cutoff-df.date).dt.days.to_numpy()/self.config.half_life_days)
        reg=self.config.regularization
        prior_mu=np.log(max(np.average(ya,weights=weights),.1));prior_home=np.log(max(np.average(yh,weights=weights),.1))-prior_mu
        x0=np.r_[np.zeros(2*n),np.full(k,prior_mu),np.full(k,prior_home)]
        def objective(x):
            eh=x[2*n+c]+x[2*n+k+c]*home_flag+x[h]+x[n+a]
            ea=x[2*n+c]+x[a]+x[n+h]
            lh=np.exp(eh);la=np.exp(ea)
            loss=np.sum(weights*(lh-yh*eh+la-ya*ea))+reg*np.dot(x[:2*n],x[:2*n])/2
            # Competition priors stabilize a new competition with only one or two rounds.
            loss+=5*np.square(x[2*n:2*n+k]-prior_mu).sum()/2+10*np.square(x[2*n+k:]-prior_home).sum()/2
            dh=weights*(lh-yh);da=weights*(la-ya)
            grad=np.r_[np.bincount(h,dh,minlength=n)+np.bincount(a,da,minlength=n)+reg*x[:n],
                np.bincount(a,dh,minlength=n)+np.bincount(h,da,minlength=n)+reg*x[n:2*n],
                np.bincount(c,dh+da,minlength=k)+5*(x[2*n:2*n+k]-prior_mu),
                np.bincount(c,dh*home_flag,minlength=k)+10*(x[2*n+k:]-prior_home)]
            return loss,grad
        opt=minimize(objective,x0,method='L-BFGS-B',jac=True,bounds=[(-2.,2.)]*(2*n)+[(-1.5,1.5)]*k+[(-.5,1.)]*k,options={'maxiter':400,'ftol':1e-10,'gtol':1e-5})
        if not opt.success:raise RuntimeError(f'Goal fit did not converge: {opt.message}')
        self.theta=opt.x;self.rho=0.;self.optimizer_iterations=int(opt.nit)
        lh=np.exp(self.theta[2*n+c]+self.theta[2*n+k+c]*home_flag+self.theta[h]+self.theta[n+a])
        la=np.exp(self.theta[2*n+c]+self.theta[a]+self.theta[n+h])
        if self.config.dixon_coles:
            lo=max(-.25,float(np.max(np.r_[-1/lh,-1/la]))+1e-8)
            hi=min(.25,float(np.min(1/(lh*la)))-1e-8)
            def correction_loss(rho):
                tau=np.ones(len(df));tau[(yh==0)&(ya==0)]=1-(lh*la*rho)[(yh==0)&(ya==0)]
                tau[(yh==0)&(ya==1)]=1+(lh*rho)[(yh==0)&(ya==1)]
                tau[(yh==1)&(ya==0)]=1+(la*rho)[(yh==1)&(ya==0)]
                tau[(yh==1)&(ya==1)]=1-rho
                return -float(np.dot(weights,np.log(tau)))+25*rho*rho
            if lo<hi:self.rho=float(minimize_scalar(correction_loss,bounds=(lo,hi),method='bounded').x)
        self.team_match_counts=pd.concat([df.home_team,df.away_team]).value_counts().to_dict()
        # Home competition anchors expose when European rates need domestic priors.
        self.team_domestic={}
        domestic=df[~df.tournament.str.contains('Champions|Europa|Conference',case=False)]
        for team,g in domestic.sort_values('date').groupby('home_team'):self.team_domestic[team]=g.tournament.iloc[-1]
        return self

    def lambdas(self,home,away,competition,neutral=False):
        n=len(self.teams);k=len(self.competitions);ci=self.competitions.get(competition)
        if ci is None:
            # Unobserved competition: prior from the two clubs' domestic environments.
            cs=[self.competitions[self.team_domestic[t]] for t in [home,away] if t in self.team_domestic]
            mu=float(np.mean(self.theta[2*n+np.array(cs)])) if cs else float(np.mean(self.theta[2*n:2*n+k]))
            adv=float(np.mean(self.theta[2*n+k+np.array(cs)])) if cs else float(np.mean(self.theta[2*n+k:]))
        else:mu=self.theta[2*n+ci];adv=self.theta[2*n+k+ci]
        def strength(t,defence=False):return self.theta[self.teams[t]+(n if defence else 0)] if t in self.teams else 0.
        return (float(np.exp(mu+(0 if neutral else adv)+strength(home)+strength(away,True))),
                float(np.exp(mu+strength(away)+strength(home,True))))

    def predict(self,home,away,competition,neutral=False):
        lh,la=self.lambdas(home,away,competition,neutral)
        out=market_summary(lh,la,self.rho)
        out.update(lam_home=lh,lam_away=la,rho=self.rho,unknown_teams=[t for t in [home,away] if t not in self.teams],competition_prior=competition not in self.competitions)
        return out

    def metadata(self):
        return {'version':MODEL_VERSION,'config':asdict(self.config),'training_cutoff':str(self.cutoff.date()),'latest_training_result':str(self.latest.date()),'training_matches':self.n_matches,'rho':self.rho,'optimizer_iterations':self.optimizer_iterations}
