# Image commune a spark-master, aux workers, au History Server et a Jupyter.
# Base : Spark 3.5.7 avec Python (la meme que dans les TP).
FROM apache/spark:3.5.7-python3

USER root
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# Delta Lake : les jars sont mis directement dans Spark a la construction.
# Plus besoin de --packages ni d'Internet au lancement des notebooks.
ADD --chmod=644 https://repo1.maven.org/maven2/io/delta/delta-spark_2.12/3.2.0/delta-spark_2.12-3.2.0.jar /opt/spark/jars/
ADD --chmod=644 https://repo1.maven.org/maven2/io/delta/delta-storage/3.2.0/delta-storage-3.2.0.jar /opt/spark/jars/

# pandas + pyarrow : export des tables gold en Parquet (couche de service)
# jupyterlab : les notebooks (le driver Spark tourne dans le conteneur jupyter)
# plotly + streamlit : graphiques et dashboard
# delta-spark : l'API Python DeltaTable (MERGE, historique). --no-deps car pyspark est deja dans l'image.
RUN pip3 install --no-cache-dir pandas==2.0.3 pyarrow==14.0.2 jupyterlab==4.2.5 \
        plotly==5.24.1 streamlit==1.39.0 \
 && pip3 install --no-cache-dir --no-deps delta-spark==3.2.0 \
 && mkdir -p /home/spark && chown -R spark:spark /home/spark

ENV PYTHONPATH=/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.7-src.zip \
    HOME=/home/spark PYSPARK_PYTHON=python3 PYSPARK_DRIVER_PYTHON=python3

# verification a la construction : la construction echoue si un import ne marche pas
RUN python3 -c "import pyspark, delta, pandas, pyarrow, plotly, streamlit; print('pyspark', pyspark.__version__)"

USER spark
WORKDIR /work
