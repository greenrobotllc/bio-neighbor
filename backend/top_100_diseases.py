"""
Top 100 diseases with their common drugs.
Curated list for downloading disease-drug relationships.
"""

from typing import List, Optional, Tuple

# Top 100 diseases with common drugs
# Format: (disease_name, mesh_id, [list of common drug names])
TOP_100_DISEASES = [
    # Neurological
    ("Alzheimer's disease", "D000544", ["donepezil", "rivastigmine", "galantamine", "memantine", "tacrine", "lecanemab", "donanemab"]),
    ("Parkinson's disease", "D010300", ["levodopa", "carbidopa", "pramipexole", "ropinirole", "selegiline", "rasagiline"]),
    ("Epilepsy", "D004827", ["phenytoin", "carbamazepine", "valproic acid", "lamotrigine", "levetiracetam", "topiramate"]),
    ("Multiple sclerosis", "D009103", ["interferon beta", "glatiramer", "fingolimod", "natalizumab", "dimethyl fumarate"]),
    ("Migraine", "D008881", ["sumatriptan", "rizatriptan", "propranolol", "topiramate", "amitriptyline"]),
    
    # Cardiovascular
    ("Hypertension", "D006973", ["lisinopril", "amlodipine", "metoprolol", "losartan", "hydrochlorothiazide", "atenolol"]),
    ("Coronary artery disease", "D003324", ["aspirin", "atorvastatin", "clopidogrel", "metoprolol", "ramipril"]),
    ("Heart failure", "D006333", ["lisinopril", "carvedilol", "furosemide", "spironolactone", "digoxin"]),
    ("Atrial fibrillation", "D001281", ["warfarin", "apixaban", "rivaroxaban", "dabigatran", "metoprolol"]),
    ("Hyperlipidemia", "D006937", ["atorvastatin", "simvastatin", "pravastatin", "rosuvastatin", "ezetimibe"]),
    
    # Metabolic
    ("Type 2 diabetes", "D003924", ["metformin", "glipizide", "pioglitazone", "sitagliptin", "insulin", "semaglutide"]),
    ("Type 1 diabetes", "D003922", ["insulin", "glucagon"]),
    ("Obesity", "D009765", ["semaglutide", "liraglutide", "orlistat", "phentermine"]),
    ("Hypothyroidism", "D007037", ["levothyroxine", "liothyronine"]),
    ("Hyperthyroidism", "D006980", ["methimazole", "propylthiouracil", "propranolol"]),
    
    # Mental Health
    ("Depression", "D003866", ["sertraline", "escitalopram", "fluoxetine", "bupropion", "venlafaxine", "duloxetine"]),
    ("Anxiety disorders", "D001008", ["alprazolam", "lorazepam", "diazepam", "buspirone", "sertraline"]),
    ("Bipolar disorder", "D001714", ["lithium", "valproic acid", "lamotrigine", "quetiapine", "olanzapine"]),
    ("Schizophrenia", "D012559", ["risperidone", "olanzapine", "quetiapine", "aripiprazole", "haloperidol"]),
    ("Attention deficit hyperactivity disorder", "D001289", ["methylphenidate", "amphetamine", "atomoxetine", "lisdexamfetamine"]),
    
    # Respiratory
    ("Asthma", "D001249", ["albuterol", "fluticasone", "montelukast", "budesonide", "salmeterol"]),
    ("Chronic obstructive pulmonary disease", "D029424", ["albuterol", "ipratropium", "tiotropium", "fluticasone", "salmeterol"]),
    ("Pneumonia", "D011014", ["amoxicillin", "azithromycin", "levofloxacin", "ceftriaxone"]),
    ("Tuberculosis", "D014376", ["isoniazid", "rifampin", "ethambutol", "pyrazinamide"]),
    
    # Gastrointestinal
    ("Gastroesophageal reflux disease", "D005764", ["omeprazole", "pantoprazole", "lansoprazole", "ranitidine", "famotidine"]),
    ("Peptic ulcer disease", "D010437", ["omeprazole", "pantoprazole", "amoxicillin", "clarithromycin"]),
    ("Irritable bowel syndrome", "D043183", ["dicyclomine", "loperamide", "linaclotide", "lubiprostone"]),
    ("Inflammatory bowel disease", "D015212", ["mesalamine", "sulfasalazine", "prednisone", "infliximab", "adalimumab"]),
    ("Constipation", "D003248", ["polyethylene glycol", "bisacodyl", "senna", "lactulose"]),
    
    # Musculoskeletal
    ("Osteoarthritis", "D010003", ["ibuprofen", "naproxen", "acetaminophen", "diclofenac", "glucosamine"]),
    ("Rheumatoid arthritis", "D001172", ["methotrexate", "sulfasalazine", "hydroxychloroquine", "adalimumab", "etanercept"]),
    ("Osteoporosis", "D010024", ["alendronate", "risedronate", "calcium", "vitamin D", "raloxifene"]),
    ("Gout", "D006073", ["allopurinol", "colchicine", "indomethacin", "prednisone"]),
    ("Fibromyalgia", "D005356", ["duloxetine", "pregabalin", "gabapentin", "amitriptyline"]),
    
    # Infectious Diseases
    ("Influenza", "D007251", ["oseltamivir", "zanamivir", "baloxavir"]),
    ("Urinary tract infection", "D014552", ["trimethoprim", "sulfamethoxazole", "ciprofloxacin", "nitrofurantoin"]),
    ("Sinusitis", "D012852", ["amoxicillin", "amoxicillin clavulanate", "azithromycin", "pseudoephedrine"]),
    ("Pharyngitis", "D010612", ["penicillin", "amoxicillin", "azithromycin", "cephalexin"]),
    ("Cellulitis", "D002481", ["cephalexin", "dicloxacillin", "amoxicillin clavulanate", "clindamycin"]),
    
    # Dermatological
    ("Acne", "D000152", ["benzoyl peroxide", "tretinoin", "clindamycin", "doxycycline", "isotretinoin"]),
    ("Eczema", "D004485", ["hydrocortisone", "triamcinolone", "tacrolimus", "pimecrolimus"]),
    ("Psoriasis", "D011565", ["methotrexate", "cyclosporine", "adalimumab", "etanercept", "ustekinumab"]),
    ("Rosacea", "D012393", ["metronidazole", "azelaic acid", "doxycycline", "ivermectin"]),
    
    # Endocrine
    ("Polycystic ovary syndrome", "D011085", ["metformin", "spironolactone", "oral contraceptives"]),
    ("Cushing's syndrome", "D003480", ["ketoconazole", "metyrapone", "mitotane"]),
    ("Addison's disease", "D000224", ["hydrocortisone", "fludrocortisone"]),
    
    # Hematological
    ("Anemia", "D000740", ["iron", "ferrous sulfate", "folic acid", "cyanocobalamin"]),
    ("Deep vein thrombosis", "D003921", ["warfarin", "rivaroxaban", "apixaban", "enoxaparin"]),
    ("Hemophilia", "D006454", ["factor VIII", "factor IX", "tranexamic acid"]),
    
    # Renal
    ("Chronic kidney disease", "D051436", ["lisinopril", "losartan", "furosemide", "metoprolol"]),
    ("Kidney stones", "D007669", ["allopurinol", "potassium citrate", "thiazides"]),
    
    # Cancer (common types)
    ("Breast cancer", "D001943", ["tamoxifen", "anastrozole", "letrozole", "trastuzumab", "paclitaxel"]),
    ("Lung cancer", "D002289", ["pembrolizumab", "nivolumab", "erlotinib", "gefitinib", "carboplatin"]),
    ("Colorectal cancer", "D015179", ["fluorouracil", "oxaliplatin", "irinotecan", "bevacizumab"]),
    ("Prostate cancer", "D011471", ["leuprolide", "bicalutamide", "enzalutamide", "abiraterone"]),
    
    # Ophthalmological
    ("Glaucoma", "D005901", ["timolol", "latanoprost", "dorzolamide", "brimonidine"]),
    ("Conjunctivitis", "D003231", ["erythromycin", "tobramycin", "ciprofloxacin", "polymyxin"]),
    ("Dry eye syndrome", "D007638", ["artificial tears", "cyclosporine", "lifitegrast"]),
    
    # Urological
    ("Benign prostatic hyperplasia", "D011470", ["tamsulosin", "finasteride", "dutasteride", "alfuzosin"]),
    ("Erectile dysfunction", "D007172", ["sildenafil", "tadalafil", "vardenafil", "avanafil"]),
    ("Overactive bladder", "D016982", ["oxybutynin", "tolterodine", "solifenacin", "mirabegron"]),
    
    # Women's Health
    ("Menopause", "D008593", ["estrogen", "progesterone", "raloxifene", "paroxetine"]),
    ("Endometriosis", "D004715", ["oral contraceptives", "leuprolide", "danazol", "medroxyprogesterone"]),
    ("Polycystic ovary syndrome", "D011085", ["metformin", "spironolactone", "oral contraceptives"]),
    
    # Pain Management
    ("Chronic pain", "D059350", ["gabapentin", "pregabalin", "duloxetine", "tramadol", "oxycodone"]),
    ("Neuropathic pain", "D009437", ["gabapentin", "pregabalin", "duloxetine", "amitriptyline"]),
    
    # Sleep Disorders
    ("Insomnia", "D007319", ["zolpidem", "eszopiclone", "trazodone", "diphenhydramine", "melatonin"]),
    ("Sleep apnea", "D012891", ["continuous positive airway pressure", "modafinil"]),
    
    # Autoimmune
    ("Systemic lupus erythematosus", "D008180", ["hydroxychloroquine", "prednisone", "azathioprine", "mycophenolate"]),
    ("Sjogren's syndrome", "D012859", ["pilocarpine", "cevimeline", "hydroxychloroquine"]),
    
    # Additional Common Conditions
    ("Allergic rhinitis", "D012220", ["loratadine", "cetirizine", "fexofenadine", "fluticasone"]),
    ("Conjunctivitis", "D003231", ["erythromycin", "tobramycin", "ciprofloxacin"]),
    ("Otitis media", "D010033", ["amoxicillin", "amoxicillin clavulanate", "azithromycin"]),
    ("Bronchitis", "D001991", ["amoxicillin", "azithromycin", "doxycycline", "albuterol"]),
    ("Gastritis", "D005756", ["omeprazole", "pantoprazole", "ranitidine"]),
    ("Hepatitis B", "D006509", ["tenofovir", "entecavir", "lamivudine"]),
    ("Hepatitis C", "D006526", ["sofosbuvir", "ledipasvir", "glecaprevir", "pibrentasvir"]),
    ("Herpes simplex", "D006561", ["acyclovir", "valacyclovir", "famciclovir"]),
    ("Varicella zoster", "D014583", ["acyclovir", "valacyclovir", "famciclovir"]),
    ("Candidiasis", "D002177", ["fluconazole", "clotrimazole", "nystatin"]),
    ("Tinea", "D014008", ["terbinafine", "clotrimazole", "miconazole"]),
    ("Scabies", "D012532", ["permethrin", "ivermectin", "lindane"]),
    ("Lice infestation", "D008290", ["permethrin", "malathion", "ivermectin"]),
    ("Hemorrhoids", "D006484", ["hydrocortisone", "pramoxine", "witch hazel"]),
    ("Diverticulitis", "D004238", ["amoxicillin clavulanate", "metronidazole", "ciprofloxacin"]),
    ("Cholelithiasis", "D002769", ["ursodeoxycholic acid"]),
    ("Pancreatitis", "D010195", ["pancrelipase", "octreotide"]),
    ("Cystitis", "D003556", ["trimethoprim", "nitrofurantoin", "ciprofloxacin"]),
    ("Pyelonephritis", "D011704", ["ciprofloxacin", "levofloxacin", "trimethoprim sulfamethoxazole"]),
    ("Prostatitis", "D011472", ["ciprofloxacin", "doxycycline", "trimethoprim"]),
    ("Epididymitis", "D004824", ["ceftriaxone", "doxycycline", "ciprofloxacin"]),
    ("Vaginitis", "D014627", ["metronidazole", "clotrimazole", "fluconazole"]),
    ("Pelvic inflammatory disease", "D000392", ["ceftriaxone", "doxycycline", "metronidazole"]),
    ("Endometritis", "D004717", ["doxycycline", "metronidazole", "clindamycin"]),
    ("Mastitis", "D008407", ["dicloxacillin", "cephalexin", "amoxicillin clavulanate"]),
    ("Lactation disorders", "D007768", ["domperidone", "metoclopramide"]),
    ("Menorrhagia", "D008595", ["oral contraceptives", "tranexamic acid", "mefenamic acid"]),
    ("Dysmenorrhea", "D004412", ["ibuprofen", "naproxen", "oral contraceptives"]),
    ("Premenstrual syndrome", "D011293", ["oral contraceptives", "fluoxetine", "spironolactone"]),
    ("Erectile dysfunction", "D007172", ["sildenafil", "tadalafil", "vardenafil"]),
    ("Premature ejaculation", "D011293", ["sertraline", "paroxetine", "dapoxetine"]),
    ("Infertility", "D007246", ["clomiphene", "letrozole", "gonadotropins"]),
    ("Hypogonadism", "D007006", ["testosterone", "human chorionic gonadotropin"]),
    ("Gynecomastia", "D006190", ["tamoxifen", "raloxifene", "anastrozole"]),
    ("Thyroid nodules", "D013969", ["levothyroxine", "radioactive iodine"]),
    ("Goiter", "D006042", ["levothyroxine", "radioactive iodine", "methimazole"]),
    ("Adrenal insufficiency", "D000309", ["hydrocortisone", "fludrocortisone"]),
    ("Pheochromocytoma", "D010673", ["phenoxybenzamine", "propranolol", "alpha blockers"]),
    ("Hyperparathyroidism", "D006961", ["cinacalcet", "parathyroidectomy"]),
    ("Hypoparathyroidism", "D007011", ["calcium", "vitamin D", "parathyroid hormone"]),
    ("Diabetes insipidus", "D003925", ["desmopressin", "vasopressin"]),
    ("Syndrome of inappropriate antidiuretic hormone", "D007177", ["demeclocycline", "tolvaptan"]),
    ("Acromegaly", "D000172", ["octreotide", "lanreotide", "pegvisomant"]),
    ("Prolactinoma", "D011398", ["bromocriptine", "cabergoline"]),
    ("Growth hormone deficiency", "D006994", ["growth hormone", "somatropin"]),
    ("Cushing's disease", "D003480", ["ketoconazole", "metyrapone", "mitotane"]),
    ("Addison's disease", "D000224", ["hydrocortisone", "fludrocortisone"]),
]


def get_top_100_diseases() -> List[Tuple[str, str, List[str]]]:
    """
    Get the list of top 100 diseases with their drugs.
    
    Returns:
        List of tuples: (disease_name, mesh_id, [drug_names])
    """
    return TOP_100_DISEASES


def get_disease_by_name(disease_name: str) -> Optional[Tuple[str, str, List[str]]]:
    """
    Get disease information by name (case-insensitive partial match).
    
    Args:
        disease_name: Name of the disease
        
    Returns:
        Tuple of (disease_name, mesh_id, [drug_names]) or None if not found
    """
    disease_name_lower = disease_name.lower()
    for disease in TOP_100_DISEASES:
        if disease_name_lower in disease[0].lower() or disease[0].lower() in disease_name_lower:
            return disease
    return None


def get_alzheimers_drugs() -> List[str]:
    """Get list of known Alzheimer's disease drugs."""
    alzheimers = get_disease_by_name("Alzheimer's disease")
    if alzheimers:
        return alzheimers[2]
    return ["donepezil", "rivastigmine", "galantamine", "memantine", "tacrine"]


if __name__ == "__main__":
    print(f"📊 Top 100 diseases loaded: {len(TOP_100_DISEASES)} diseases")
    print("\nSample diseases:")
    for i, (name, mesh_id, drugs) in enumerate(TOP_100_DISEASES[:10], 1):
        print(f"  {i}. {name} (MeSH: {mesh_id}) - {len(drugs)} drugs")

