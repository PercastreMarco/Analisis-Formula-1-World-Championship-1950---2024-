
import kagglehub

# Download latest version
DATA_PATH = kagglehub.dataset_download("rohanrao/formula-1-world-championship-1950-2020")

print("Path to dataset files:", DATA_PATH)
