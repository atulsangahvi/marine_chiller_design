# Marine Seawater / Water-Cooled AC Package Design Checker

This Streamlit app accepts PDF outputs from:
- Compressor selection software
- Shell-and-tube condenser design app
- Evaporator coil / evaporator design app

It checks:
- Compressor effective SST/SCT after refrigerant pressure drops
- Remaining subcooling at EEV
- Chilled water and seawater flow
- Water pipe velocity
- Low-load risk
- Bypass / optional circuit requirements
- Preliminary P&ID logic
- Preliminary BOM
- Control sequence diagram

## Install

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit secrets

Create `.streamlit/secrets.toml`:

```toml
APP_PASSWORD = "change-this-password"
```

## GitHub / Streamlit Cloud

Push these files to GitHub, then connect the repository to Streamlit Cloud.
Add `APP_PASSWORD` in Streamlit Cloud > App settings > Secrets.

## Important

This is a design-checking framework, not a final certified design tool. Final pressure vessel, relief valve, electrical and marine class approval checks must be done before manufacturing.