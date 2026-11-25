"""Generate only fictional, non-sensitive deployment PDFs and a fixed run policy."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import os

import pymupdf


def scanned_page(document, text):
    temporary=pymupdf.open()
    page=temporary.new_page(width=612,height=792)
    page.insert_textbox((50,50,562,742),text,fontsize=17,fontname='helv')
    image=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False)
    document.new_page(width=612,height=792).insert_image(page.rect,stream=image.tobytes('png'))
    temporary.close()


def prepare(destination:Path,run_id:str):
    if not re.fullmatch(r'aws-demo-\d{8}-live-\d{2}',run_id):
        raise ValueError('fresh aws-demo-YYYYMMDD-live-NN identity required')
    destination.mkdir(mode=0o700,parents=True,exist_ok=False)
    policy=json.loads((Path(__file__).with_name('acceptance-policy.json')).read_text())
    policy['run_id']=run_id
    with (destination/'acceptance-policy.json').open('x') as output:
        json.dump(policy,output,indent=2);output.write('\n')
    career=('Morgan Vale\nFull Stack Engineer\nProfessional summary\n'
            'Morgan Vale is a Full Stack Engineer with five years of experience at Cedar Labs.\n'
            'PROJECTS\nAtlas project at Cedar Labs\n'
            'The Atlas project reduced report preparation time from 40 minutes to 12 minutes.\n'
            'Work included Python, PostgreSQL, FastAPI, React, and a reporting dashboard.\n')
    resume=pymupdf.open();page=resume.new_page(width=612,height=792)
    page.insert_textbox((50,50,562,742),career,fontsize=17)
    scanned_page(resume,'EDUCATION\nBachelor of Engineering in Computer Engineering\n'
                 'Sample Institute of Technology\n2016 - 2020\n\n'
                 'CERTIFICATIONS\nPostgreSQL certificate, 2023\n')
    resume.save(destination/'Browser_Check_Morgan_Vale.pdf');resume.close()
    policy_pdf=pymupdf.open()
    scanned_page(policy_pdf,'ASTER HARBOR VISITOR POLICY\n\n'
                 'A visitor day pass costs 83 credits.\n'
                 'The pass is valid for 17 days from issue.\n')
    policy_pdf.save(destination/'Aster_Harbor_Policy.pdf');policy_pdf.close()
    deletion=pymupdf.open()
    for number in range(1,9):
        scanned_page(deletion,f'SYNTHETIC DELETION FENCE PAGE {number}\n\n'+
                     'A fictional queue job must not recreate a deleted document.\n'*12)
    deletion.save(destination/'Deletion_Fence_Scan.pdf',deflate=True);deletion.close()
    manifest={file.name:{'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'bytes':file.stat().st_size}
              for file in sorted(destination.iterdir()) if file.is_file()}
    with (destination/'fixture-manifest.json').open('x') as output:
        json.dump(manifest,output,indent=2);output.write('\n')
    for file in destination.iterdir():file.chmod(0o600)
    return {'status':'PASS','run_id':run_id,'destination':str(destination),'files':manifest}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    arguments=parser.parse_args();os.umask(0o077)
    print(json.dumps(prepare(arguments.destination,arguments.run_id)))
