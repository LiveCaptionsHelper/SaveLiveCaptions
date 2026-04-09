'''
This module contains the configuration for the function app.
'''
# Configuration for texthook

# The threshold for considering sentences as stable
# default is 3, meaning a sentence must be observed 3 times to be considered stable
STABLE_THRESHOLD = 3  

# The maximum number of saved sentences to keep in memory
# default is 50
MAX_SAVED_SENTENCES = 50  

# The minimum length of a sentence to be considered for saving
# default is 10 characters
MIN_LENGTH=10

# WHEN TEXTHOOKING the similarity threshold for considering two sentences as similar 
# default is 0.85, meaning sentences with similarity above 0.85 will be considered similar
SIMILARITY=0.85