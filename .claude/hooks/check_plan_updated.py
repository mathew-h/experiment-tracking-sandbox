import os
import sys
import time

def main():
    try:
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        plans_dir = os.path.join(PROJECT_ROOT, "docs", "superpowers", "plans")
        
        if not os.path.exists(plans_dir):
            sys.exit(0)
            
        recent_modification = False
        current_time = time.time()
        # N minutes threshold (e.g., 60 minutes)
        threshold = 60 * 60
        
        for filename in os.listdir(plans_dir):
            if filename.endswith(".md"):
                file_path = os.path.join(plans_dir, filename)
                mtime = os.path.getmtime(file_path)
                if current_time - mtime < threshold:
                    recent_modification = True
                    break
                    
        if not recent_modification:
            print("⚠️  Warning: No plans in docs/superpowers/plans/ have been updated in the last hour.", file=sys.stderr)
            print("   Don't forget to update the plan before committing!", file=sys.stderr)
            
    except Exception:
        pass

if __name__ == "__main__":
    main()
    sys.exit(0)
