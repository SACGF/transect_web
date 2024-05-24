r = getOption("repos")
r["CRAN"] = "http://cran.us.r-project.org"
options(repos = r)

if (!require("BiocManager", quietly = TRUE))
    install.packages("BiocManager")

BiocManager::install("edgeR")
BiocManager::install("Glimma")
BiocManager::install("recount") # needed for RECOUNT3
BiocManager::install("recount3") # needed for RECOUNT3
BiocManager::install("DEFormats") # needed for RECOUNT3

install.packages("pacman", repos = "http://cran.us.r-project.org")
install.packages("dplyr", repos = "http://cran.us.r-project.org")
install.packages("tidyr", repos = "http://cran.us.r-project.org")
install.packages("data.table", repos = "http://cran.us.r-project.org")
install.packages("tibble", repos = "http://cran.us.r-project.org")
install.packages("svglite", repos = "http://cran.us.r-project.org")
install.packages("ggplot2", repos = "http://cran.us.r-project.org")
install.packages("ggforce", repos = "http://cran.us.r-project.org")
install.packages("calibrate", repos = "http://cran.us.r-project.org")
install.packages("gplots", repos = "http://cran.us.r-project.org")
install.packages("RColorBrewer", repos = "http://cran.us.r-project.org")
install.packages("plotly", repos="http://cran.us.r-project.org", dependencies=TRUE)
install.packages('htmlwidgets', repos="http://cran.us.r-project.org")