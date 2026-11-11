from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
import backend.config.settings as s
cfg = s.get_settings() if hasattr(s, 'get_settings') else s.settings
URL = make_url(cfg.database_url).set(database='experiments_audit168')
assert URL.database == 'experiments_audit168'
engine = create_engine(URL)
