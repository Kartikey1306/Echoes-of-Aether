"""Contact sheet of files matching a glob:  Blender -b --python sheet_glob.py -- "<glob>" out.png cols w h"""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artkit as A
a = A.args()
A.contact_sheet(sorted(glob.glob(a[0])), a[1], cols=int(a[2]), cell=(int(a[3]), int(a[4])))
