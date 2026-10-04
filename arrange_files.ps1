# Run inside the folder where you saved all the downloaded files.
# It builds the correct folder structure in a new subfolder called "repo".
$r = "repo"
"app","tests","scripts","data","notebooks",".github\workflows" | % { New-Item -ItemType Directory -Force -Path "$r\$_" | Out-Null }
"main.py","filing.py","normalize.py","auth.py","config.py","cds_hooks.py","__init__.py" | % { Copy-Item $_ "$r\app\" }
"conftest.py","test_api.py","test_cds_hooks.py","test_filing.py","test_normalize.py" | % { Copy-Item $_ "$r\tests\" }
"demo_local.py","gen_keys.py","evaluate_filing.py","build_icd10_dataset.py","coverage_icd10.py" | % { Copy-Item $_ "$r\scripts\" }
"coverage_by_chapter.csv","general_blocks.csv","gold_template.csv" | % { Copy-Item $_ "$r\data\" }
Copy-Item "ehr_plugin_colab_demo.ipynb" "$r\notebooks\"
Copy-Item "ci.yml" "$r\.github\workflows\"
".env.example",".gitignore","Dockerfile","docker-compose.yml","EVALUATION.md","LICENSE","README.md","requirements.txt","requirements-dev.txt" | % { Copy-Item $_ "$r\" }
Write-Host "Done. Your upload-ready folder is: $((Resolve-Path $r).Path)"
dir $r -Recurse -Force -File | Select-Object -ExpandProperty FullName
