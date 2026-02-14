import sys
import os
sys.path.append(os.getcwd())

from connectors import list_available_series, get_connector

def verify_connectors():
    series_list = list_available_series()
    
    # Check NASCAR
    nascar_found = False
    for s in series_list:
        if s.series_id == "nascar_cup":
            nascar_found = True
            print(f"✅ Found series: {s.name} ({s.series_id})")
            
    # Check SRO
    sro_found = False
    for s in series_list:
        if s.series_id == "gtwc_europe":
            sro_found = True
            print(f"✅ Found series: {s.name} ({s.series_id})")

    # Check New Batches
    wec_found = False
    wrc_found = False
    supercars_found = False
    sf_found = False
    
    for s in series_list:
        if s.series_id == "wec":
            wec_found = True
            print(f"✅ Found series: {s.name} ({s.series_id})")
        if s.series_id == "wrc":
            wrc_found = True
            print(f"✅ Found series: {s.name} ({s.series_id})")
        if s.series_id == "supercars":
            supercars_found = True
            print(f"✅ Found series: {s.name} ({s.series_id})")
        if s.series_id == "super_formula":
            sf_found = True
            print(f"✅ Found series: {s.name} ({s.series_id})")

    if not nascar_found:
        print("❌ NASCAR Cup Series not found")
    if not sro_found:
        print("❌ GT World Challenge Europe not found")
    if not wec_found:
        print("❌ WEC not found")
    if not wrc_found:
        print("❌ WRC not found")
    if not supercars_found:
        print("❌ Supercars not found")
    if not sf_found:
        print("❌ Super Formula not found")

    # Check URL resolution
    if nascar_found:
        c = get_connector("nascar")
        print(f"✅ Connector 'nascar' loaded: {c.name}")
        
    if sro_found:
        c = get_connector("sro_gt")
        print(f"✅ Connector 'sro_gt' loaded: {c.name}")
        
    if wec_found:
        c = get_connector("endurance")
        print(f"✅ Connector 'endurance' loaded: {c.name}")


if __name__ == "__main__":
    verify_connectors()
