"""Open a clean personal workspace and preserve existing personal records."""
import sys
from launch import main
if __name__=='__main__':sys.argv=[sys.argv[0],'personal',*sys.argv[1:]];main()
